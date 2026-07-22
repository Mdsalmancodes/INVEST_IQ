"""Unit tests for RealPriceProvider — the Phase 4 integration point that
replaces Portfolio's NullPriceProvider stub, verified against the exact
contract Portfolio's PriceProvider Protocol requires (returns None rather
than raising when no price is available)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.domain.market_data.entities import OhlcvBar
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import InstrumentId, Interval, Price
from src.infrastructure.market_data.real_price_provider import RealPriceProvider

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_ID = InstrumentId(uuid.uuid4())


def make_bar(bar_time: datetime, adjusted_close: str) -> OhlcvBar:
    return OhlcvBar(
        instrument_id=INSTRUMENT_ID,
        interval=Interval.ONE_DAY,
        bar_time=bar_time,
        open=Price(Decimal("100")),
        high=Price(Decimal("110")),
        low=Price(Decimal("95")),
        close=Price(Decimal(adjusted_close)),
        adjusted_close=Price(Decimal(adjusted_close)),
        volume=1000,
        is_closed=True,
        source="test",
        created_at=bar_time,
    )


class FakeOhlcvBarRepository:
    def __init__(self, bars: list[OhlcvBar] | None = None) -> None:
        self._bars = bars or []

    async def save(self, bar: OhlcvBar) -> None:
        self._bars.append(bar)

    async def save_many(self, bars: tuple[OhlcvBar, ...]) -> None:
        self._bars.extend(bars)

    async def query(self, query: OhlcvBarQuery) -> tuple[OhlcvBar, ...]:
        matching = [
            b
            for b in self._bars
            if b.instrument_id == query.instrument_id and b.interval == query.interval
        ]
        return tuple(sorted(matching, key=lambda b: b.bar_time))

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        matching = [
            b for b in self._bars if b.instrument_id == instrument_id and b.interval == interval
        ]
        if not matching:
            return None
        return max(matching, key=lambda b: b.bar_time)

    async def apply_adjustment_factor_before_date(
        self, instrument_id: InstrumentId, before: date, factor: Decimal
    ) -> int:
        return 0


@pytest.mark.asyncio
class TestGetCurrentPrice:
    async def test_returns_latest_closed_bar_adjusted_close(self) -> None:
        repo = FakeOhlcvBarRepository(
            [
                make_bar(datetime(2026, 1, 1, tzinfo=UTC), "100"),
                make_bar(datetime(2026, 1, 2, tzinfo=UTC), "105"),
            ]
        )
        provider = RealPriceProvider(repo)

        price = await provider.get_current_price(INSTRUMENT_ID)

        assert price is not None
        assert price.amount == Decimal("105.00000000")

    async def test_returns_none_when_no_bars_exist(self) -> None:
        repo = FakeOhlcvBarRepository([])
        provider = RealPriceProvider(repo)

        price = await provider.get_current_price(INSTRUMENT_ID)

        assert price is None


@pytest.mark.asyncio
class TestGetPreviousClose:
    async def test_returns_second_to_last_bar_adjusted_close(self) -> None:
        repo = FakeOhlcvBarRepository(
            [
                make_bar(datetime(2026, 1, 1, tzinfo=UTC), "100"),
                make_bar(datetime(2026, 1, 2, tzinfo=UTC), "105"),
            ]
        )
        provider = RealPriceProvider(repo)

        previous_close = await provider.get_previous_close(INSTRUMENT_ID)

        assert previous_close is not None
        assert previous_close.amount == Decimal("100.00000000")

    async def test_returns_none_when_fewer_than_two_bars_exist(self) -> None:
        repo = FakeOhlcvBarRepository([make_bar(datetime(2026, 1, 1, tzinfo=UTC), "100")])
        provider = RealPriceProvider(repo)

        previous_close = await provider.get_previous_close(INSTRUMENT_ID)

        assert previous_close is None

    async def test_returns_none_when_no_bars_exist(self) -> None:
        repo = FakeOhlcvBarRepository([])
        provider = RealPriceProvider(repo)

        previous_close = await provider.get_previous_close(INSTRUMENT_ID)

        assert previous_close is None
