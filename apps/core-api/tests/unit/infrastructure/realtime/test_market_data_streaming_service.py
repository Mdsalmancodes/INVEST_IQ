"""Tests for MarketDataStreamingService — real ConnectionManager (pure,
no network), real GetMarketStatusUseCase (pure, no I/O), fakes for
everything else (provider, cache, repositories), following the
established Phase 4 test-double convention (FakeInstrumentRepository/
FakeOhlcvBarRepository, matching test_use_cases.py's own fakes)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.market_data.provider import BarResult, QuoteResult
from src.application.market_data.provider_router import ProviderRouter
from src.domain.market_data.entities import AssetType, Instrument, OhlcvBar
from src.domain.market_data.exceptions import NoQuoteAvailableError
from src.domain.market_data.value_objects import InstrumentId, Interval, Price
from src.infrastructure.market_data.cache import MarketDataCache
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.market_data_streaming_service import MarketDataStreamingService

NOW = datetime(2026, 1, 1, tzinfo=UTC)
AAPL_ID = InstrumentId(uuid.uuid4())


class FakeWebSocket:
    async def accept(self) -> None:
        pass

    async def send_json(self, message: dict[str, object]) -> None:
        pass


class FakeRedisBroker:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    async def publish(self, channel: str, payload: dict[str, object]) -> None:
        self.published.append((channel, payload))


class FakeInstrumentRepository:
    def __init__(self, instruments: list[Instrument]) -> None:
        self._instruments = instruments

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        return next((i for i in self._instruments if i.symbol == symbol), None)


class FakeOhlcvBarRepository:
    def __init__(self, bars: list[OhlcvBar]) -> None:
        self._bars = bars

    async def get_latest_closed_bar(
        self, instrument_id: InstrumentId, interval: Interval
    ) -> OhlcvBar | None:
        matching = [b for b in self._bars if b.instrument_id == instrument_id]
        return matching[-1] if matching else None


class FakeQuoteProvider:
    def __init__(
        self, should_fail: bool = False, price: str = "150", previous_close: str = "145"
    ) -> None:
        self._should_fail = should_fail
        self._price = price
        self._previous_close = previous_close

    @property
    def name(self) -> str:
        return "fake"

    async def get_quote(self, symbol: str) -> QuoteResult:
        if self._should_fail:
            raise NoQuoteAvailableError("simulated failure")
        return QuoteResult(
            symbol=symbol,
            price=Price(Decimal(self._price)),
            previous_close=Price(Decimal(self._previous_close)),
            as_of=NOW,
            source="fake",
        )

    async def get_bars(self, *args: object, **kwargs: object) -> tuple[BarResult, ...]:
        return ()


def _make_instrument(symbol: str = "AAPL") -> Instrument:
    return Instrument(
        id=AAPL_ID,
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


def _make_bar(
    open_price: str = "148", high: str = "152", low: str = "147", close: str = "150"
) -> OhlcvBar:
    return OhlcvBar(
        instrument_id=AAPL_ID,
        interval=Interval.ONE_DAY,
        bar_time=NOW,
        open=Price(Decimal(open_price)),
        high=Price(Decimal(high)),
        low=Price(Decimal(low)),
        close=Price(Decimal(close)),
        adjusted_close=Price(Decimal(close)),
        volume=123456,
        is_closed=True,
        source="fake",
        created_at=NOW,
    )


class FakeRedisCache:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, str]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return self._store.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str]) -> int:
        self._store.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        return True


def _build_service(
    connection_manager: ConnectionManager,
    redis_broker: FakeRedisBroker,
    instruments: list[Instrument],
    bars: list[OhlcvBar],
    quote_provider: FakeQuoteProvider,
) -> MarketDataStreamingService:
    instrument_repo = FakeInstrumentRepository(instruments)
    bar_repo = FakeOhlcvBarRepository(bars)

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[object]:
        yield object()

    return MarketDataStreamingService(
        connection_manager=connection_manager,
        redis_broker=redis_broker,  # type: ignore[arg-type]
        session_scope=session_scope,
        repository_factory=lambda _session: (instrument_repo, bar_repo),  # type: ignore[arg-type,return-value]
        provider_router=ProviderRouter(
            quote_providers=(quote_provider,), historical_providers=(quote_provider,)
        ),
        market_data_cache=MarketDataCache(FakeRedisCache()),  # type: ignore[arg-type]
        market_status_use_case=GetMarketStatusUseCase(),
        poll_interval_seconds=5.0,
    )


class TestTick:
    async def test_always_publishes_market_status_to_the_ticker_channel(self) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        service = _build_service(manager, broker, [], [], FakeQuoteProvider())

        await service.tick()

        ticker_messages = [p for c, p in broker.published if c == channels.TICKER_CHANNEL]
        assert len(ticker_messages) == 1
        assert "is_open" in ticker_messages[0]
        assert "session" in ticker_messages[0]

    async def test_publishes_nothing_for_symbols_when_no_client_is_subscribed(self) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        service = _build_service(
            manager, broker, [_make_instrument()], [_make_bar()], FakeQuoteProvider()
        )

        await service.tick()

        quote_messages = [c for c, _ in broker.published if c.startswith("realtime:quote:")]
        assert quote_messages == []

    async def test_publishes_a_quote_tick_for_every_subscribed_symbol(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["quote:AAPL"])
        broker = FakeRedisBroker()
        service = _build_service(
            manager,
            broker,
            [_make_instrument()],
            [_make_bar()],
            FakeQuoteProvider(price="150", previous_close="145"),
        )

        await service.tick()

        quote_entries = [(c, p) for c, p in broker.published if c == channels.quote_channel("AAPL")]
        assert len(quote_entries) == 1
        _, payload = quote_entries[0]
        assert payload["symbol"] == "AAPL"
        assert Decimal(str(payload["price"])) == Decimal("150")
        assert Decimal(str(payload["open"])) == Decimal("148")
        assert Decimal(str(payload["high"])) == Decimal("152")
        assert Decimal(str(payload["low"])) == Decimal("147")
        assert payload["volume"] == 123456
        assert Decimal(str(payload["previous_close"])) == Decimal("145")
        assert Decimal(str(payload["change"])) == Decimal("5")
        assert Decimal(str(payload["change_pct"])).quantize(Decimal("0.01")) == Decimal("3.45")

    async def test_a_failed_quote_for_one_symbol_does_not_prevent_others_from_publishing(
        self,
    ) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["quote:AAPL", "quote:MSFT"])
        broker = FakeRedisBroker()
        # AAPL exists and has a working provider; MSFT has no instrument at
        # all, so GetCurrentPriceUseCase raises — this should not stop
        # AAPL's tick from still being published this cycle.
        service = _build_service(
            manager, broker, [_make_instrument("AAPL")], [_make_bar()], FakeQuoteProvider()
        )

        await service.tick()

        published_channels = {c for c, _ in broker.published}
        assert channels.quote_channel("AAPL") in published_channels
        assert channels.quote_channel("MSFT") not in published_channels

    async def test_non_quote_topics_are_ignored_when_determining_symbols_to_poll(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["portfolio:some-id", "ticker"])
        broker = FakeRedisBroker()
        service = _build_service(manager, broker, [], [], FakeQuoteProvider())

        await service.tick()

        quote_messages = [c for c, _ in broker.published if c.startswith("realtime:quote:")]
        assert quote_messages == []
