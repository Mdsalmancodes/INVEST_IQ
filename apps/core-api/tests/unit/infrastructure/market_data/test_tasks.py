"""Unit tests for run_sync_pipeline — the testable core of the Celery
sync_instrument_bars task (Document 5 §11.2's ingestion pipeline), using
fakes for every dependency per the established pattern."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.application.market_data.provider import BarResult
from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.validation_service import MarketDataValidationService
from src.domain.market_data.entities import AssetType, Instrument, OhlcvBar
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import InstrumentId, Interval, Price
from src.infrastructure.market_data.tasks import run_sync_pipeline

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_ID = InstrumentId(uuid.uuid4())


def make_instrument() -> Instrument:
    return Instrument(
        id=INSTRUMENT_ID,
        symbol="AAPL",
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
        return next((i for i in self._instruments if i.id == instrument_id), None)

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        return next((i for i in self._instruments if i.symbol == symbol), None)

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        return tuple(self._instruments)


class FakeOhlcvBarRepository:
    def __init__(self) -> None:
        self.saved_batches: list[tuple[OhlcvBar, ...]] = []

    async def save(self, bar: OhlcvBar) -> None:
        self.saved_batches.append((bar,))

    async def save_many(self, bars: tuple[OhlcvBar, ...]) -> None:
        self.saved_batches.append(bars)

    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]:
        return ()

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        return None

    async def apply_adjustment_factor_before_date(
        self, instrument_id: InstrumentId, before: date, factor: Decimal
    ) -> int:
        return 0


class FakeHistoricalProvider:
    def __init__(self, bars: tuple[BarResult, ...], should_fail: bool = False) -> None:
        self._bars = bars
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake"

    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        if self._should_fail:
            raise RuntimeError("simulated provider failure")
        return self._bars


class FakeQuoteProvider:
    @property
    def name(self) -> str:
        return "fake"

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError("not used by this pipeline")


def make_bar_result(close: str = "105") -> BarResult:
    return BarResult(
        symbol="AAPL",
        interval=Interval.ONE_DAY,
        bar_time=NOW,
        open=Price(Decimal("100")),
        high=Price(Decimal("110")),
        low=Price(Decimal("95")),
        close=Price(Decimal(close)),
        volume=1000,
        is_closed=True,
        source="fake",
    )


@pytest.mark.asyncio
class TestRunSyncPipeline:
    async def test_returns_zero_when_instrument_not_found(self) -> None:
        instrument_repo = FakeInstrumentRepository([])
        ohlcv_repo = FakeOhlcvBarRepository()
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider((make_bar_result(),)),),
        )

        count = await run_sync_pipeline(
            "UNKNOWN", instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        assert count == 0
        assert len(ohlcv_repo.saved_batches) == 0

    async def test_persists_valid_bars(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository()
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider((make_bar_result(),)),),
        )

        count = await run_sync_pipeline(
            "AAPL", instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        assert count == 1
        assert len(ohlcv_repo.saved_batches) == 1
        assert ohlcv_repo.saved_batches[0][0].instrument_id == INSTRUMENT_ID

    async def test_returns_zero_when_provider_fails(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository()
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(FakeHistoricalProvider((), should_fail=True),),
        )

        count = await run_sync_pipeline(
            "AAPL", instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        assert count == 0
        assert len(ohlcv_repo.saved_batches) == 0

    async def test_invalid_bars_are_filtered_out(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository()
        bad_bar = BarResult(
            symbol="AAPL",
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("50")),  # high < low -> invalid
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="fake",
        )
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(
                FakeHistoricalProvider(
                    (bad_bar, make_bar_result()),
                ),
            ),
        )

        count = await run_sync_pipeline(
            "AAPL", instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        # only the valid bar (make_bar_result()) should be persisted
        assert count == 1

    async def test_does_not_persist_when_no_valid_bars(self) -> None:
        instrument_repo = FakeInstrumentRepository([make_instrument()])
        ohlcv_repo = FakeOhlcvBarRepository()
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider(),),
            historical_providers=(
                FakeHistoricalProvider(
                    (),
                ),
            ),
        )

        count = await run_sync_pipeline(
            "AAPL", instrument_repo, ohlcv_repo, router, MarketDataValidationService()
        )

        assert count == 0
        assert len(ohlcv_repo.saved_batches) == 0
