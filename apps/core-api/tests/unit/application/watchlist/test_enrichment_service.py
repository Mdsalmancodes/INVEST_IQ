"""Unit tests for WatchlistEnrichmentService — the Phase 4/5 integration
point. Uses fakes for GetCurrentPriceUseCase/GetMarketStatusUseCase (both
substituted at their public .execute() interface, matching how the real
use cases are consumed) and a FakeInstrumentRepository, so this test
exercises WatchlistEnrichmentService's own orchestration/mapping logic in
isolation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from src.application.market_data.get_current_price_use_case import CurrentPriceResult
from src.application.market_data.get_market_status_use_case import MarketStatusResult
from src.application.watchlist.enrichment_service import WatchlistEnrichmentService
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.market_data.value_objects import Price
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.value_objects import InstrumentId

AAPL_ID = InstrumentId(uuid.uuid4())
MSFT_ID = InstrumentId(uuid.uuid4())


class FakeInstrumentRepository:
    def __init__(self, instruments: dict[str, Instrument] | None = None) -> None:
        self._by_id = instruments or {}

    async def save(self, instrument: Instrument) -> None:
        self._by_id[str(instrument.id)] = instrument

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        return self._by_id.get(str(instrument_id))

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        raise NotImplementedError

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        raise NotImplementedError


def _instrument(instrument_id: InstrumentId, symbol: str) -> Instrument:
    return Instrument(
        id=MarketDataInstrumentId(instrument_id.value),
        symbol=symbol,
        exchange="NASDAQ",
        name=f"{symbol} Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=None,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _current_price_result(
    symbol: str,
    price: str,
    previous_close: str | None,
    source: str = "yfinance",
    is_stale_fallback: bool = False,
) -> CurrentPriceResult:
    return CurrentPriceResult(
        symbol=symbol,
        price=Price(Decimal(price)),
        previous_close=Price(Decimal(previous_close)) if previous_close else None,
        source=source,
        is_stale_fallback=is_stale_fallback,
    )


class FakeGetCurrentPriceUseCase:
    def __init__(self, results_by_symbol: dict[str, CurrentPriceResult | Exception]) -> None:
        self._results_by_symbol = results_by_symbol

    async def execute(self, symbol: str) -> CurrentPriceResult:
        result = self._results_by_symbol[symbol]
        if isinstance(result, Exception):
            raise result
        return result


class FakeGetMarketStatusUseCase:
    def __init__(self, session: str = "open") -> None:
        self._session = session

    def execute(self) -> MarketStatusResult:
        return MarketStatusResult(
            is_open=self._session == "open",
            session=self._session,
            as_of=datetime.now(UTC),
            next_open=None,
        )


class TestWatchlistEnrichmentService:
    async def test_enriches_all_items_successfully(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        watchlist.add_item(AAPL_ID)
        watchlist.add_item(MSFT_ID)

        instrument_repo = FakeInstrumentRepository(
            {
                str(AAPL_ID): _instrument(AAPL_ID, "AAPL"),
                str(MSFT_ID): _instrument(MSFT_ID, "MSFT"),
            }
        )
        price_use_case = FakeGetCurrentPriceUseCase(
            {
                "AAPL": _current_price_result("AAPL", "150.00", "145.00"),
                "MSFT": _current_price_result("MSFT", "300.00", "310.00"),
            }
        )
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase("open"),
        )

        enriched = await service.enrich(watchlist)

        assert enriched.market_status == "open"
        assert len(enriched.quotes_by_item_id) == 2

        aapl_item = next(i for i in watchlist.items if i.instrument_id == AAPL_ID)
        aapl_quote = enriched.quotes_by_item_id[str(aapl_item.id)]
        assert aapl_quote.price == Decimal("150.00")
        assert aapl_quote.daily_change == Decimal("5.00")
        assert aapl_quote.is_delayed is False
        assert aapl_quote.error is None

        msft_item = next(i for i in watchlist.items if i.instrument_id == MSFT_ID)
        msft_quote = enriched.quotes_by_item_id[str(msft_item.id)]
        assert msft_quote.daily_change == Decimal("-10.00")

    async def test_computes_daily_change_pct(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(AAPL_ID)

        instrument_repo = FakeInstrumentRepository({str(AAPL_ID): _instrument(AAPL_ID, "AAPL")})
        price_use_case = FakeGetCurrentPriceUseCase(
            {"AAPL": _current_price_result("AAPL", "110.00", "100.00")}
        )
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase(),
        )

        enriched = await service.enrich(watchlist)

        quote = enriched.quotes_by_item_id[str(item.id)]
        assert quote.daily_change_pct == Decimal("10.00")

    async def test_marks_stale_fallback_as_delayed(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(AAPL_ID)

        instrument_repo = FakeInstrumentRepository({str(AAPL_ID): _instrument(AAPL_ID, "AAPL")})
        price_use_case = FakeGetCurrentPriceUseCase(
            {"AAPL": _current_price_result("AAPL", "150.00", None, is_stale_fallback=True)}
        )
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase(),
        )

        enriched = await service.enrich(watchlist)

        quote = enriched.quotes_by_item_id[str(item.id)]
        assert quote.is_delayed is True
        assert quote.daily_change is None  # no previous_close available

    async def test_isolates_per_item_quote_failure(self) -> None:
        """One symbol's quote-fetch failure must not break enrichment for
        the rest of the watchlist's items — the founder's error-isolation
        requirement, verified directly."""
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        watchlist.add_item(AAPL_ID)
        watchlist.add_item(MSFT_ID)

        instrument_repo = FakeInstrumentRepository(
            {
                str(AAPL_ID): _instrument(AAPL_ID, "AAPL"),
                str(MSFT_ID): _instrument(MSFT_ID, "MSFT"),
            }
        )
        price_use_case = FakeGetCurrentPriceUseCase(
            {
                "AAPL": RuntimeError("provider network error"),
                "MSFT": _current_price_result("MSFT", "300.00", "310.00"),
            }
        )
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase(),
        )

        enriched = await service.enrich(watchlist)

        aapl_item = next(i for i in watchlist.items if i.instrument_id == AAPL_ID)
        msft_item = next(i for i in watchlist.items if i.instrument_id == MSFT_ID)

        aapl_quote = enriched.quotes_by_item_id[str(aapl_item.id)]
        assert aapl_quote.error == "provider network error"
        assert aapl_quote.price is None

        msft_quote = enriched.quotes_by_item_id[str(msft_item.id)]
        assert msft_quote.error is None
        assert msft_quote.price == Decimal("300.00")

    async def test_handles_deleted_instrument_still_referenced_by_item(self) -> None:
        """An instrument can be deactivated/deleted after being watchlisted
        — this must be reported as a per-item error, not raised."""
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        item = watchlist.add_item(AAPL_ID)

        instrument_repo = FakeInstrumentRepository({})  # AAPL_ID intentionally absent
        price_use_case = FakeGetCurrentPriceUseCase({})
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase(),
        )

        enriched = await service.enrich(watchlist)

        quote = enriched.quotes_by_item_id[str(item.id)]
        assert quote.error == "Instrument no longer exists"
        assert quote.symbol is None

    async def test_market_status_passes_through(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Watchlist")
        instrument_repo = FakeInstrumentRepository({})
        price_use_case = FakeGetCurrentPriceUseCase({})
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase("after-hours"),
        )

        enriched = await service.enrich(watchlist)

        assert enriched.market_status == "after-hours"

    async def test_empty_watchlist_enriches_to_no_quotes(self) -> None:
        watchlist = Watchlist.create(user_id="user-1", name="Empty Watchlist")
        instrument_repo = FakeInstrumentRepository({})
        price_use_case = FakeGetCurrentPriceUseCase({})
        service = WatchlistEnrichmentService(
            instrument_repo,
            price_use_case,
            FakeGetMarketStatusUseCase(),
        )

        enriched = await service.enrich(watchlist)

        assert enriched.quotes_by_item_id == {}
