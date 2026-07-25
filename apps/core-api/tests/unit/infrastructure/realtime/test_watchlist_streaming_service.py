"""Tests for WatchlistStreamingService — real ConnectionManager, real
Watchlist/WatchlistItem entities, real WatchlistEnrichmentService (all
pure, no I/O), fakes only for the repository/use-case boundary, matching
test_enrichment_service.py's own established convention."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from src.application.market_data.get_current_price_use_case import CurrentPriceResult
from src.application.market_data.get_market_status_use_case import MarketStatusResult
from src.application.watchlist.enrichment_service import WatchlistEnrichmentService
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.market_data.value_objects import Price
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistListFilter, WatchlistPageResult
from src.domain.watchlist.value_objects import InstrumentId
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.watchlist_streaming_service import (
    WatchlistStreamingDependencies,
    WatchlistStreamingService,
)

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
    def __init__(self, instruments: dict[str, Instrument]) -> None:
        self._by_id = instruments

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        return self._by_id.get(str(instrument_id))


class FakeGetCurrentPriceUseCase:
    def __init__(self, price: str = "150", previous_close: str = "145") -> None:
        self._price = price
        self._previous_close = previous_close

    async def execute(self, symbol: str) -> CurrentPriceResult:
        return CurrentPriceResult(
            symbol=symbol,
            price=Price(Decimal(self._price)),
            previous_close=Price(Decimal(self._previous_close)),
            source="fake",
            is_stale_fallback=False,
        )


class FakeGetMarketStatusUseCase:
    def execute(self) -> MarketStatusResult:
        return MarketStatusResult(is_open=True, session="open", as_of=NOW, next_open=None)


class FakeWatchlistRepository:
    def __init__(self, watchlists_by_user: dict[str, list[Watchlist]]) -> None:
        self._watchlists_by_user = watchlists_by_user

    async def list_for_user(
        self, user_id: str, filters: WatchlistListFilter
    ) -> WatchlistPageResult:
        items = tuple(self._watchlists_by_user.get(user_id, []))
        return WatchlistPageResult(
            items=items, total_count=len(items), page=filters.page, page_size=filters.page_size
        )


def _instrument(symbol: str = "AAPL") -> Instrument:
    return Instrument(
        id=MarketDataInstrumentId(AAPL_ID.value),
        symbol=symbol,
        exchange="NASDAQ",
        name=f"{symbol} Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=None,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=NOW,
    )


def _watchlist_with_one_item(user_id: str) -> Watchlist:
    watchlist = Watchlist.create(user_id=user_id, name="My Watchlist")
    watchlist.add_item(AAPL_ID)
    return watchlist


def _build_service(
    connection_manager: ConnectionManager,
    redis_broker: FakeRedisBroker,
    watchlists_by_user: dict[str, list[Watchlist]],
    instruments: dict[str, Instrument] | None = None,
) -> WatchlistStreamingService:
    watchlist_repo = FakeWatchlistRepository(watchlists_by_user)
    instrument_repo = FakeInstrumentRepository(instruments or {str(AAPL_ID): _instrument()})

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[object]:
        yield object()

    def dependency_factory(_session: object) -> WatchlistStreamingDependencies:
        return WatchlistStreamingDependencies(
            watchlist_repository=watchlist_repo,  # type: ignore[arg-type]
            enrichment_service=WatchlistEnrichmentService(
                instrument_repo,  # type: ignore[arg-type]
                FakeGetCurrentPriceUseCase(),
                FakeGetMarketStatusUseCase(),
            ),
        )

    return WatchlistStreamingService(
        connection_manager=connection_manager,
        redis_broker=redis_broker,  # type: ignore[arg-type]
        session_scope=session_scope,
        dependency_factory=dependency_factory,
        poll_interval_seconds=10.0,
    )


class TestTick:
    async def test_publishes_nothing_when_no_client_is_subscribed_to_watchlist(self) -> None:
        manager = ConnectionManager()
        broker = FakeRedisBroker()
        service = _build_service(manager, broker, {"user-1": [_watchlist_with_one_item("user-1")]})

        await service.tick()

        assert broker.published == []

    async def test_publishes_an_enriched_watchlist_for_a_subscribed_user(self) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["watchlist"])
        broker = FakeRedisBroker()
        watchlist = _watchlist_with_one_item("user-1")
        service = _build_service(manager, broker, {"user-1": [watchlist]})

        await service.tick()

        matching = [
            (c, p) for c, p in broker.published if c == channels.watchlist_channel("user-1")
        ]
        assert len(matching) == 1
        _, payload = matching[0]
        assert payload["watchlist_id"] == str(watchlist.id)
        assert payload["market_status"] == "open"
        items = payload["items"]
        assert len(items) == 1  # type: ignore[arg-type]
        item = items[0]  # type: ignore[index]
        assert item["symbol"] == "AAPL"
        assert Decimal(str(item["price"])) == Decimal("150")
        assert Decimal(str(item["daily_change"])) == Decimal("5")

    async def test_does_not_publish_for_a_user_not_subscribed_even_if_others_are(self) -> None:
        manager = ConnectionManager()
        subs_one = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subs_one.subscribe(["watchlist"])
        await manager.connect("user-2", FakeWebSocket())  # type: ignore[arg-type]
        broker = FakeRedisBroker()
        service = _build_service(
            manager,
            broker,
            {
                "user-1": [_watchlist_with_one_item("user-1")],
                "user-2": [_watchlist_with_one_item("user-2")],
            },
        )

        await service.tick()

        published_channels = {c for c, _ in broker.published}
        assert channels.watchlist_channel("user-1") in published_channels
        assert channels.watchlist_channel("user-2") not in published_channels

    async def test_one_watchlists_enrichment_failure_does_not_block_the_users_other_watchlists(
        self,
    ) -> None:
        manager = ConnectionManager()
        subscriptions = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subscriptions.subscribe(["watchlist"])
        broker = FakeRedisBroker()
        # Second watchlist references an instrument id with no matching
        # Instrument row — WatchlistEnrichmentService itself tolerates this
        # per-item (reports an error on that item), so this should not
        # even raise; included to prove tick() overall still publishes
        # both watchlists rather than aborting on the first anomaly.
        good_watchlist = _watchlist_with_one_item("user-1")
        other_watchlist = Watchlist.create(user_id="user-1", name="Other")
        other_watchlist.add_item(InstrumentId(uuid.uuid4()))
        service = _build_service(manager, broker, {"user-1": [good_watchlist, other_watchlist]})

        await service.tick()

        matching = [c for c, _ in broker.published if c == channels.watchlist_channel("user-1")]
        assert len(matching) == 2
