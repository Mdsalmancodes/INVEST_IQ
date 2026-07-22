"""Unit tests for the market_data use cases — GetCurrentPrice,
GetOhlcvBars, GetHistoricalPrices, GetCorporateActions. Uses fakes for
every dependency, following the established Phase 3 pattern."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.application.market_data.get_corporate_actions_use_case import (
    GetCorporateActionsUseCase,
)
from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_historical_prices_use_case import (
    GetHistoricalPricesUseCase,
)
from src.application.market_data.get_ohlcv_bars_use_case import GetOhlcvBarsUseCase
from src.application.market_data.provider import BarResult, QuoteResult
from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.validation_service import MarketDataValidationService
from src.domain.market_data.entities import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    Instrument,
    OhlcvBar,
)
from src.domain.market_data.exceptions import InstrumentNotFoundError, NoQuoteAvailableError
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval, Price
from src.infrastructure.market_data.cache import MarketDataCache

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_ID = InstrumentId(uuid.uuid4())


def make_instrument(symbol: str = "AAPL") -> Instrument:
    return Instrument(
        id=INSTRUMENT_ID,
        symbol=symbol,
        exchange="NASDAQ",
        name="Apple Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=None,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=NOW,
    )


class FakeInstrumentRepository:
    def __init__(self, instruments: list[Instrument] | None = None) -> None:
        self._instruments = instruments or []

    async def save(self, instrument: Instrument) -> None:
        self._instruments.append(instrument)

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        for i in self._instruments:
            if i.id == instrument_id:
                return i
        return None

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        for i in self._instruments:
            if i.symbol == symbol:
                return i
        return None

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        return tuple(i for i in self._instruments if query.lower() in i.symbol.lower())


class FakeOhlcvBarRepository:
    def __init__(self, bars: list[OhlcvBar] | None = None) -> None:
        self._bars = bars or []
        self.saved_batches: list[tuple[OhlcvBar, ...]] = []

    async def save(self, bar: OhlcvBar) -> None:
        self._bars.append(bar)

    async def save_many(self, bars: tuple[OhlcvBar, ...]) -> None:
        self.saved_batches.append(bars)
        self._bars.extend(bars)

    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]:
        return tuple(
            b
            for b in self._bars
            if b.instrument_id == query.instrument_id and b.interval == query.interval
        )

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        matching = [
            b
            for b in self._bars
            if b.instrument_id == instrument_id and b.interval == interval and b.is_closed
        ]
        if not matching:
            return None
        return max(matching, key=lambda b: b.bar_time)

    async def apply_adjustment_factor_before_date(
        self, instrument_id: InstrumentId, before: date, factor: Decimal
    ) -> int:
        return 0


class FakeCorporateActionRepository:
    def __init__(self, actions: list[CorporateAction] | None = None) -> None:
        self._actions = actions or []

    async def save(self, action: CorporateAction) -> None:
        self._actions.append(action)

    async def get_by_id(self, action_id: CorporateActionId) -> CorporateAction | None:
        return next((a for a in self._actions if a.id == action_id), None)

    async def list_for_instrument(self, instrument_id: InstrumentId) -> tuple[CorporateAction, ...]:
        return tuple(a for a in self._actions if a.instrument_id == instrument_id)

    async def exists(self, instrument_id: InstrumentId, action_type: str, ex_date: date) -> bool:
        return any(
            a.instrument_id == instrument_id
            and a.action_type.value == action_type
            and a.ex_date == ex_date
            for a in self._actions
        )


class FakeQuoteProvider:
    def __init__(self, should_fail: bool = False, price: str = "150") -> None:
        self._should_fail = should_fail
        self._price = price

    @property
    def name(self) -> str:
        return "fake"

    async def get_quote(self, symbol: str) -> QuoteResult:
        if self._should_fail:
            raise NoQuoteAvailableError("simulated failure")
        return QuoteResult(
            symbol=symbol,
            price=Price(Decimal(self._price)),
            previous_close=Price(Decimal("145")),
            as_of=NOW,
            source="fake",
        )


class FakeHistoricalProvider:
    def __init__(self, bars: tuple[BarResult, ...] | None = None) -> None:
        self._bars = bars if bars is not None else self._default_bars()

    @property
    def name(self) -> str:
        return "fake"

    def _default_bars(self) -> tuple[BarResult, ...]:
        return (
            BarResult(
                symbol="AAPL",
                interval=Interval.ONE_DAY,
                bar_time=NOW,
                open=Price(Decimal("100")),
                high=Price(Decimal("110")),
                low=Price(Decimal("95")),
                close=Price(Decimal("105")),
                volume=1000,
                is_closed=True,
                source="fake",
            ),
        )

    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        return self._bars


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return self._store.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self._store.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        return True


@pytest.mark.asyncio
class TestGetCurrentPriceUseCase:
    async def test_returns_cached_quote_if_present(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        cache = MarketDataCache(FakeRedis())  # type: ignore[arg-type]
        await cache.set_quote(
            QuoteResult(
                symbol="AAPL",
                price=Price(Decimal("160")),
                previous_close=None,
                as_of=NOW,
                source="cached",
            )
        )
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(price="999"),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetCurrentPriceUseCase(instrument_repo, FakeOhlcvBarRepository(), router, cache)

        result = await use_case.execute("AAPL")

        assert result.price.amount == Decimal("160.00000000")
        assert result.is_stale_fallback is False

    async def test_fetches_from_provider_on_cache_miss(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        cache = MarketDataCache(FakeRedis())  # type: ignore[arg-type]
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(price="150"),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetCurrentPriceUseCase(instrument_repo, FakeOhlcvBarRepository(), router, cache)

        result = await use_case.execute("AAPL")

        assert result.price.amount == Decimal("150.00000000")

    async def test_falls_back_to_last_closed_bar_when_provider_fails(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        cache = MarketDataCache(FakeRedis())  # type: ignore[arg-type]
        bar = OhlcvBar(
            instrument_id=INSTRUMENT_ID,
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("108")),
            adjusted_close=Price(Decimal("108")),
            volume=1000,
            is_closed=True,
            source="fake",
            created_at=NOW,
        )
        ohlcv_repo = FakeOhlcvBarRepository([bar])
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(should_fail=True),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetCurrentPriceUseCase(instrument_repo, ohlcv_repo, router, cache)

        result = await use_case.execute("AAPL")

        assert result.price.amount == Decimal("108.00000000")
        assert result.is_stale_fallback is True

    async def test_raises_when_instrument_not_found(self) -> None:
        instrument_repo = FakeInstrumentRepository([])
        cache = MarketDataCache(FakeRedis())  # type: ignore[arg-type]
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetCurrentPriceUseCase(instrument_repo, FakeOhlcvBarRepository(), router, cache)

        with pytest.raises(InstrumentNotFoundError):
            await use_case.execute("UNKNOWN")


@pytest.mark.asyncio
class TestGetOhlcvBarsUseCase:
    async def test_returns_existing_bars_from_repository(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        bar = OhlcvBar(
            instrument_id=INSTRUMENT_ID,
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            adjusted_close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="fake",
            created_at=NOW,
        )
        ohlcv_repo = FakeOhlcvBarRepository([bar])
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetOhlcvBarsUseCase(
            instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        result = await use_case.execute(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result.bars) == 1
        assert result.data_completeness == "complete"

    async def test_fetches_and_persists_from_provider_on_empty_coverage(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository([])
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        use_case = GetOhlcvBarsUseCase(
            instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        result = await use_case.execute(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result.bars) == 1
        assert len(ohlcv_repo.saved_batches) == 1

    async def test_rejects_invalid_bars_from_provider(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository([])
        bad_bar = BarResult(
            symbol="AAPL",
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("50")),  # high < low, invalid — but Price ctor allows it
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="fake",
        )
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider(bars=(bad_bar,)),),
        )
        use_case = GetOhlcvBarsUseCase(
            instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        result = await use_case.execute(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result.bars) == 0
        assert result.data_completeness == "partial"


@pytest.mark.asyncio
class TestGetHistoricalPricesUseCase:
    async def test_returns_adjusted_close_points(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        bar = OhlcvBar(
            instrument_id=INSTRUMENT_ID,
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            adjusted_close=Price(Decimal("103")),
            volume=1000,
            is_closed=True,
            source="fake",
            created_at=NOW,
        )
        ohlcv_repo = FakeOhlcvBarRepository([bar])
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider(),),
        )
        ohlcv_use_case = GetOhlcvBarsUseCase(
            instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )
        use_case = GetHistoricalPricesUseCase(ohlcv_use_case)

        result = await use_case.execute(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result.points) == 1
        assert result.points[0].price.amount == Decimal("103.00000000")


@pytest.mark.asyncio
class TestGetCorporateActionsUseCase:
    async def test_returns_actions_for_instrument(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        action = CorporateAction(
            id=CorporateActionId.new(),
            instrument_id=INSTRUMENT_ID,
            action_type=CorporateActionType.SPLIT,
            ratio=Decimal("2"),
            cash_amount=None,
            ex_date=date(2026, 1, 1),
            announced_at=None,
            created_at=NOW,
        )
        action_repo = FakeCorporateActionRepository([action])
        use_case = GetCorporateActionsUseCase(instrument_repo, action_repo)

        result = await use_case.execute("AAPL")

        assert len(result) == 1
        assert result[0].action_type == CorporateActionType.SPLIT

    async def test_raises_when_instrument_not_found(self) -> None:
        instrument_repo = FakeInstrumentRepository([])
        action_repo = FakeCorporateActionRepository([])
        use_case = GetCorporateActionsUseCase(instrument_repo, action_repo)

        with pytest.raises(InstrumentNotFoundError):
            await use_case.execute("UNKNOWN")
