"""RedisBroker — thin Pub/Sub wrapper over the EXISTING redis-broker
instance (RedisClients.broker, already used by Celery — see
src/infrastructure/persistence/redis/clients.py's own docstring, which
designates this exact instance for "Celery + Alert Streams"). No new
Redis instance is introduced for Phase 9; this reuses the architecture's
own already-declared intent for this instance.

WHY REDIS PUB/SUB (not a new message queue, not Redis Streams): the
architecture doc's own phrase "Alert Streams" plus this being the
simplest mechanism that satisfies the founder's explicit "Redis Pub/Sub"
requirement. Pub/Sub messages are fire-and-forget (no durability, no
replay) — acceptable here because every publish in this phase is a
"here is the current state" snapshot (a price tick, a portfolio
recalculation), not an event a consumer must never miss; a client that
was briefly disconnected simply gets the NEXT tick, and the reconnection
flow (frontend, task 11) re-fetches current state via the normal REST
endpoints on reconnect rather than relying on catching up via missed
Pub/Sub messages.

HORIZONTAL SCALABILITY: every core-api process instance runs its own
RedisBroker + ConnectionManager pair. publish() sends to Redis; every
subscribed instance's listener (subscribe_and_dispatch) receives the
same message and fans it out to whichever of ITS OWN locally-connected
clients care about that channel. This is what makes N running instances
behave as one logical real-time layer without instances needing to know
about each other directly.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

from observability import get_logger
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = get_logger(__name__)

MessageHandler = Callable[[str, dict[str, object]], Awaitable[None]]
"""Called with (channel, decoded_payload) for every message received on
a subscribed channel."""


class RedisBroker:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(self, channel: str, payload: dict[str, object]) -> None:
        """Fire-and-forget publish. Failures are logged, not raised — a
        Redis Pub/Sub outage must degrade to "no live updates delivered
        this tick" for connected clients, never crash the caller (the
        market-data streaming loop, the alert evaluation loop, etc.),
        mirroring the same fail-open principle Phase 8's RateLimitMiddleware
        established for this exact kind of best-effort infrastructure
        dependency."""
        try:
            await self._redis.publish(channel, json.dumps(payload))
        except RedisError as exc:
            logger.warning("realtime.publish_failed", channel=channel, error=str(exc))

    async def subscribe_and_dispatch(
        self, channels: list[str], handler: MessageHandler, *, stop_event: asyncio.Event
    ) -> None:
        """Runs until `stop_event` is set (used for graceful shutdown from
        main.py's lifespan) or the connection is fatally lost. Each
        received message is decoded from JSON and passed to `handler`;
        a malformed payload is logged and skipped rather than crashing
        the whole listener loop over one bad message."""
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(*channels)
            await self._pump(pubsub, handler, stop_event)
        finally:
            await pubsub.unsubscribe(*channels)
            await self._close(pubsub)

    async def psubscribe_and_dispatch(
        self, patterns: list[str], handler: MessageHandler, *, stop_event: asyncio.Event
    ) -> None:
        """Same contract as subscribe_and_dispatch, but for Redis Pub/Sub
        glob PATTERNS (psubscribe) — used by RealtimeService to receive
        every symbol's "realtime:quote:*"-shaped channel with a single
        registration, without needing to know in advance which symbols
        exist. `handler` receives the concrete channel name the message
        was actually published on (e.g. "realtime:quote:AAPL"), not the
        pattern itself."""
        pubsub = self._redis.pubsub()
        try:
            await pubsub.psubscribe(*patterns)
            await self._pump(pubsub, handler, stop_event)
        finally:
            await pubsub.punsubscribe(*patterns)
            await self._close(pubsub)

    async def _pump(
        self, pubsub: object, handler: MessageHandler, stop_event: asyncio.Event
    ) -> None:
        while not stop_event.is_set():
            try:
                message = await pubsub.get_message(  # type: ignore[attr-defined]
                    ignore_subscribe_messages=True, timeout=1.0
                )
            except RedisError as exc:
                logger.warning("realtime.subscribe_error", error=str(exc))
                await asyncio.sleep(1.0)
                continue
            if message is None:
                continue
            channel = message["channel"]
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("realtime.malformed_message", channel=channel, error=str(exc))
                continue
            await handler(channel, payload)

    async def _close(self, pubsub: object) -> None:
        # redis-py's PubSub.aclose() ships with no type stub for this
        # session's installed version — a genuine third-party gap (same
        # category as yfinance/celery/testcontainers, already
        # scoped-ignored in pyproject.toml's [[tool.mypy.overrides]] for
        # module-level imports; aclose() is a single call site, not a
        # whole-module import, so a targeted ignore here is more precise
        # than adding another module-level override).
        await pubsub.aclose()  # type: ignore[attr-defined]
