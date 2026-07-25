"""WatchlistStreamingService — Phase 9's "Live Watchlist" requirement:
price changes, gain/loss, no page refresh, for every watchlist a
connected user has open.

Reuses the EXISTING WatchlistEnrichmentService (Phase 5, unmodified) —
this service's only job is deciding WHEN to re-run it and WHERE to
publish the result, not recomputing anything Phase 5 doesn't already
compute. Every item's live price/daily-change/daily-change-pct/market-
status/delayed-indicator already comes from that unmodified service.

WHY A SEPARATE POLL LOOP/INTERVAL FROM MarketDataStreamingService (task
3): watchlist enrichment is more expensive per tick (N items x a full
GetCurrentPriceUseCase call each, via WatchlistEnrichmentService) than a
single symbol's quote lookup, and doesn't need to feel as instantaneous
as the raw ticker — settings.realtime_watchlist_poll_interval_seconds
(default 10s, longer than market data's 5s) is a disclosed, deliberate
choice to reduce redundant work, not an oversight. The two loops
NATURALLY reuse the same underlying MarketDataCache (redis-cache, 30s
TTL) that GetCurrentPriceUseCase always checks first, so most watchlist
enrichment ticks are cheap cache hits rather than fresh provider calls,
even though this service's own poll interval is independent from task
3's.

Each tick, for every user with at least one connection subscribed to
the "watchlist" topic (ConnectionManager.user_ids_subscribed_to), loads
that user's watchlists (WatchlistRepository.list_for_user — EXISTING,
unmodified) and enriches each one, publishing the result to
channels.watchlist_channel(user_id).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from decimal import Decimal

from observability import get_logger

from src.application.watchlist.enrichment_service import (
    EnrichedWatchlist,
    ItemQuote,
    WatchlistEnrichmentService,
)
from src.domain.watchlist.repositories import WatchlistListFilter, WatchlistRepository
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker

logger = get_logger(__name__)

_WATCHLIST_TOPIC = "watchlist"
_MAX_WATCHLISTS_PER_USER_PER_TICK = 50
"""Matches the existing pagination page_size ceiling used elsewhere in
this codebase (e.g. notification/portfolio list endpoints' le=100 — this
is set lower since a user with more than 50 watchlists is not a realistic
case this phase needs to optimize for, and this bounds one user's tick
cost)."""


def _enriched_watchlist_to_payload(enriched: EnrichedWatchlist) -> dict[str, object]:
    return {
        "watchlist_id": str(enriched.watchlist.id),
        "name": enriched.watchlist.name,
        "market_status": enriched.market_status,
        "items": [
            _item_quote_to_payload(item_id, quote)
            for item_id, quote in enriched.quotes_by_item_id.items()
        ],
    }


def _item_quote_to_payload(item_id: str, quote: ItemQuote) -> dict[str, object]:
    return {
        "item_id": item_id,
        "symbol": quote.symbol,
        "price": _decimal_to_str(quote.price),
        "previous_close": _decimal_to_str(quote.previous_close),
        "daily_change": _decimal_to_str(quote.daily_change),
        "daily_change_pct": _decimal_to_str(quote.daily_change_pct),
        "is_delayed": quote.is_delayed,
        "error": quote.error,
    }


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


@dataclass(frozen=True, slots=True)
class WatchlistStreamingDependencies:
    """Bundles the per-tick, per-session dependencies WatchlistEnrichmentService
    needs — constructed fresh per tick from a fresh session, exactly like
    MarketDataStreamingService's own per-tick repository construction
    (task 3), never held open across the whole background loop's
    lifetime."""

    watchlist_repository: WatchlistRepository
    enrichment_service: WatchlistEnrichmentService


DependencyFactory = Callable[[object], WatchlistStreamingDependencies]
"""Given a session, returns the dependencies this service needs for that
tick — kept as a plain Callable (not importing concrete SQLAlchemy
repository classes into this module) so tests can substitute fakes
without a real database session. Production wiring (main.py's lifespan)
passes a factory that constructs the real SqlAlchemy* repository and
wires it into a real WatchlistEnrichmentService alongside the existing
GetCurrentPriceUseCase/GetMarketStatusUseCase."""


class WatchlistStreamingService:
    def __init__(
        self,
        connection_manager: ConnectionManager,
        redis_broker: RedisBroker,
        session_scope: Callable[[], AbstractAsyncContextManager[object]],
        dependency_factory: DependencyFactory,
        poll_interval_seconds: float,
    ) -> None:
        self._connection_manager = connection_manager
        self._redis_broker = redis_broker
        self._session_scope = session_scope
        self._dependency_factory = dependency_factory
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - one bad tick must
                # never kill the whole streaming loop.
                logger.warning("realtime.watchlist.tick_failed", error=str(exc))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)

    async def tick(self) -> None:
        """Runs exactly one poll cycle — public so tests can invoke a
        single tick deterministically."""
        user_ids = self._connection_manager.user_ids_subscribed_to(_WATCHLIST_TOPIC)
        if not user_ids:
            return

        async with self._session_scope() as session:
            deps = self._dependency_factory(session)
            for user_id in user_ids:
                await self._publish_for_user(user_id, deps)

    async def _publish_for_user(self, user_id: str, deps: WatchlistStreamingDependencies) -> None:
        try:
            page = await deps.watchlist_repository.list_for_user(
                user_id, WatchlistListFilter(page=1, page_size=_MAX_WATCHLISTS_PER_USER_PER_TICK)
            )
        except Exception as exc:  # noqa: BLE001 - isolate one user's
            # failure from every other subscribed user's tick this cycle.
            logger.warning("realtime.watchlist.list_failed", user_id=user_id, error=str(exc))
            return

        for watchlist in page.items:
            try:
                enriched = await deps.enrichment_service.enrich(watchlist)
            except Exception as exc:  # noqa: BLE001 - isolate one
                # watchlist's failure from the user's other watchlists.
                logger.warning(
                    "realtime.watchlist.enrich_failed",
                    user_id=user_id,
                    watchlist_id=str(watchlist.id),
                    error=str(exc),
                )
                continue
            await self._redis_broker.publish(
                channels.watchlist_channel(user_id), _enriched_watchlist_to_payload(enriched)
            )
