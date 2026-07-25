"""ConnectionManager — tracks active WebSocket connections per user and
handles topic-filtered broadcast delivery.

Phase 9 (Real-Time Market Intelligence). New bounded-context-spanning
infrastructure — no prior phase built any WebSocket code (confirmed via a
full codebase search before this module was written; see
docs/phase-9/implementation-summary.md for the fuller investigation).

DESIGN — horizontal scalability: this class only tracks connections held
by THIS process. In a multi-instance deployment, a client connected to
instance A cannot be reached by a message published only to instance A's
in-memory manager. The fan-out mechanism that makes this horizontally
scalable is Redis Pub/Sub (see redis_broker.py) — every instance
subscribes to the same Redis channels and re-broadcasts to its own
locally-connected clients, so publishing a message on ANY instance
reaches EVERY instance's ConnectionManager, and therefore every
connected client regardless of which instance they're attached to. This
class itself has no Redis dependency; it is deliberately a pure,
directly-unit-testable in-memory registry — RealtimeService (the layer
above it) wires it to Redis Pub/Sub.

Supports multiple simultaneous connections per user (e.g. two browser
tabs, or a phone + laptop) — a user_id maps to a SET of (websocket,
subscriptions) entries, not a single one; closing one tab's connection
does not affect the other, and each tab can independently subscribe to
different topics (SubscriptionRegistry, one per connection).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import WebSocket
from observability import get_logger

from src.infrastructure.realtime.subscription_registry import SubscriptionRegistry

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Connection:
    websocket: WebSocket
    subscriptions: SubscriptionRegistry = field(default_factory=SubscriptionRegistry)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections_by_user: dict[str, dict[WebSocket, _Connection]] = defaultdict(dict)
        # A single lock guards mutation of the registry (connect/disconnect)
        # — broadcasts iterate a snapshot (see _snapshot_for_user) so they
        # never hold the lock while awaiting a slow client send, which
        # would otherwise let one stalled connection block delivery to
        # every other connection.
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> SubscriptionRegistry:
        await websocket.accept()
        connection = _Connection(websocket=websocket)
        async with self._lock:
            self._connections_by_user[user_id][websocket] = connection
        logger.info(
            "realtime.connection.opened",
            user_id=user_id,
            connection_count=len(self._connections_by_user[user_id]),
        )
        return connection.subscriptions

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections_by_user.get(user_id)
            if connections is None:
                return
            connections.pop(websocket, None)
            if not connections:
                del self._connections_by_user[user_id]
        logger.info("realtime.connection.closed", user_id=user_id)

    def connection_count_for_user(self, user_id: str) -> int:
        return len(self._connections_by_user.get(user_id, {}))

    def total_connection_count(self) -> int:
        return sum(len(connections) for connections in self._connections_by_user.values())

    def connected_user_ids(self) -> frozenset[str]:
        """Every user_id with at least one live connection on THIS
        instance — used by the market-data streaming loop (task 3) to
        decide which watchlist/portfolio owners actually need a poll
        tick computed for them, avoiding wasted work for users with no
        open dashboard anywhere."""
        return frozenset(self._connections_by_user.keys())

    def all_subscribed_topics(self) -> frozenset[str]:
        """Every topic string ANY connection on this instance has
        subscribed to, across all users — used by
        MarketDataStreamingService (task 3) to know exactly which
        symbols/portfolios/etc. are worth computing a fresh tick for,
        rather than polling every symbol that has ever existed regardless
        of whether any connected client cares about it right now."""
        return frozenset(
            topic
            for connections in self._connections_by_user.values()
            for c in connections.values()
            for topic in c.subscriptions.topics()
        )

    def user_ids_subscribed_to(self, topic_prefix: str) -> frozenset[str]:
        """Every user_id that has AT LEAST ONE connection (of possibly
        several — e.g. multiple tabs) subscribed to a topic starting with
        `topic_prefix` — used by WatchlistStreamingService/
        PortfolioStreamingService (tasks 4/5) to know which users' data
        is actually worth recomputing this tick, since enrichment/
        recalculation is far more expensive per-tick than a single
        symbol's quote lookup and should never run for a user with no
        dashboard open anywhere."""
        return frozenset(
            user_id
            for user_id, connections in self._connections_by_user.items()
            if any(
                topic.startswith(topic_prefix)
                for c in connections.values()
                for topic in c.subscriptions.topics()
            )
        )

    async def send_to_user(
        self, user_id: str, message: dict[str, object], *, topic: str | None = None
    ) -> None:
        """Sends `message` (as JSON) to this user's connections ON THIS
        INSTANCE. If `topic` is given, only connections subscribed to
        that topic receive it; if `topic` is None, every one of the
        user's connections receives it regardless of subscriptions
        (used for inherently-personal, always-relevant messages like
        alert triggers). Silently a no-op if the user has no matching
        connections here — callers never need to check
        connection_count_for_user() first."""
        async with self._lock:
            connections = tuple(self._connections_by_user.get(user_id, {}).values())
        targets = tuple(
            (user_id, c.websocket)
            for c in connections
            if topic is None or c.subscriptions.is_subscribed(topic)
        )
        if not targets:
            return
        await self._send_to_many(targets, message)

    async def broadcast(self, message: dict[str, object], *, topic: str | None = None) -> None:
        """Sends `message` to every connection on this instance, across
        all users, optionally filtered by topic subscription — used for
        market-wide data (e.g. index/ticker values or a symbol's quote)
        that any interested client receives regardless of their own
        portfolio or watchlist ownership."""
        async with self._lock:
            all_connections = tuple(
                (user_id, c)
                for user_id, connections in self._connections_by_user.items()
                for c in connections.values()
            )
        targets = tuple(
            (user_id, c.websocket)
            for user_id, c in all_connections
            if topic is None or c.subscriptions.is_subscribed(topic)
        )
        if not targets:
            return
        await self._send_to_many(targets, message)

    async def _send_to_many(
        self, targets: tuple[tuple[str, WebSocket], ...], message: dict[str, object]
    ) -> None:
        # A dead/stale connection's send() raises; one failure must never
        # prevent delivery to the other connections in the same batch —
        # gather with return_exceptions=True, then clean up any that
        # failed, matching the same "isolate per-item failure" principle
        # WatchlistEnrichmentService (Phase 5) already established for
        # per-symbol quote failures. Each target carries its own user_id
        # so a failed connection can always be disconnected correctly,
        # regardless of whether delivery came from send_to_user() (one
        # user) or broadcast() (all users).
        results = await asyncio.gather(
            *(websocket.send_json(message) for _, websocket in targets),
            return_exceptions=True,
        )
        for (user_id, websocket), result in zip(targets, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("realtime.send_failed", user_id=user_id, error=str(result))
                await self.disconnect(user_id, websocket)
