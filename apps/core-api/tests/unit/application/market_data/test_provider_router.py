"""Unit tests for ProviderRouter's failover logic — the core guarantee
Document 5 §11.1's provider abstraction exists to provide, so tested with
fakes covering every combination of success/failure across the chain."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.application.market_data.provider import BarResult, QuoteResult
from src.application.market_data.provider_router import ProviderRouter
from src.domain.market_data.exceptions import AllProvidersFailedError
from src.domain.market_data.value_objects import Interval, Price


class FakeQuoteProvider:
    def __init__(self, name: str, should_fail: bool = False, price: str = "100") -> None:
        self._name = name
        self._should_fail = should_fail
        self._price = price
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    async def get_quote(self, symbol: str) -> QuoteResult:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError(f"{self._name} is down")
        return QuoteResult(
            symbol=symbol,
            price=Price(Decimal(self._price)),
            previous_close=None,
            as_of=datetime.now(UTC),
            source=self._name,
        )


class FakeHistoricalProvider:
    def __init__(self, name: str, should_fail: bool = False) -> None:
        self._name = name
        self._should_fail = should_fail
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    async def get_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError(f"{self._name} is down")
        return (
            BarResult(
                symbol=symbol,
                interval=interval,
                bar_time=datetime(2026, 1, 1, tzinfo=UTC),
                open=Price(Decimal("100")),
                high=Price(Decimal("110")),
                low=Price(Decimal("95")),
                close=Price(Decimal("105")),
                volume=1000,
                is_closed=True,
                source=self._name,
            ),
        )


@pytest.mark.asyncio
class TestProviderRouterQuoteFailover:
    async def test_uses_first_provider_when_it_succeeds(self) -> None:
        primary = FakeQuoteProvider("primary", price="100")
        secondary = FakeQuoteProvider("secondary", price="200")
        router = ProviderRouter(
            quote_providers=(primary, secondary),
            historical_providers=(FakeHistoricalProvider("h"),),
        )

        result = await router.resolve_quote("AAPL")

        assert result.price.amount == Decimal("100.00000000")
        assert primary.call_count == 1
        assert secondary.call_count == 0

    async def test_falls_through_to_second_provider_on_first_failure(self) -> None:
        primary = FakeQuoteProvider("primary", should_fail=True)
        secondary = FakeQuoteProvider("secondary", price="200")
        router = ProviderRouter(
            quote_providers=(primary, secondary),
            historical_providers=(FakeHistoricalProvider("h"),),
        )

        result = await router.resolve_quote("AAPL")

        assert result.price.amount == Decimal("200.00000000")
        assert primary.call_count == 1
        assert secondary.call_count == 1

    async def test_raises_when_all_providers_fail(self) -> None:
        primary = FakeQuoteProvider("primary", should_fail=True)
        secondary = FakeQuoteProvider("secondary", should_fail=True)
        router = ProviderRouter(
            quote_providers=(primary, secondary),
            historical_providers=(FakeHistoricalProvider("h"),),
        )

        with pytest.raises(AllProvidersFailedError):
            await router.resolve_quote("AAPL")

        assert primary.call_count == 1
        assert secondary.call_count == 1

    async def test_three_provider_chain_falls_through_twice(self) -> None:
        p1 = FakeQuoteProvider("p1", should_fail=True)
        p2 = FakeQuoteProvider("p2", should_fail=True)
        p3 = FakeQuoteProvider("p3", price="300")
        router = ProviderRouter(
            quote_providers=(p1, p2, p3),
            historical_providers=(FakeHistoricalProvider("h"),),
        )

        result = await router.resolve_quote("AAPL")

        assert result.price.amount == Decimal("300.00000000")
        assert p1.call_count == 1
        assert p2.call_count == 1
        assert p3.call_count == 1


@pytest.mark.asyncio
class TestProviderRouterBarsFailover:
    async def test_uses_first_provider_when_it_succeeds(self) -> None:
        primary = FakeHistoricalProvider("primary")
        secondary = FakeHistoricalProvider("secondary")
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider("q"),),
            historical_providers=(primary, secondary),
        )

        result = await router.resolve_bars(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result) == 1
        assert primary.call_count == 1
        assert secondary.call_count == 0

    async def test_falls_through_on_failure(self) -> None:
        primary = FakeHistoricalProvider("primary", should_fail=True)
        secondary = FakeHistoricalProvider("secondary")
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider("q"),),
            historical_providers=(primary, secondary),
        )

        result = await router.resolve_bars(
            "AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10)
        )

        assert len(result) == 1
        assert result[0].source == "secondary"

    async def test_raises_when_all_fail(self) -> None:
        primary = FakeHistoricalProvider("primary", should_fail=True)
        secondary = FakeHistoricalProvider("secondary", should_fail=True)
        router = ProviderRouter(
            quote_providers=(FakeQuoteProvider("q"),),
            historical_providers=(primary, secondary),
        )

        with pytest.raises(AllProvidersFailedError):
            await router.resolve_bars("AAPL", Interval.ONE_DAY, date(2026, 1, 1), date(2026, 1, 10))


class TestProviderRouterConstruction:
    def test_requires_at_least_one_quote_provider(self) -> None:
        with pytest.raises(ValueError, match="quote provider"):
            ProviderRouter(quote_providers=(), historical_providers=(FakeHistoricalProvider("h"),))

    def test_requires_at_least_one_historical_provider(self) -> None:
        with pytest.raises(ValueError, match="historical provider"):
            ProviderRouter(quote_providers=(FakeQuoteProvider("q"),), historical_providers=())
