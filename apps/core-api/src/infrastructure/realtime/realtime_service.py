"""RealtimeService — the single process-wide listener that bridges Redis
Pub/Sub messages (published by any publisher: the market-data streaming
loop, portfolio recalculation, AI/sentiment refresh, alert evaluation)
to this instance's ConnectionManager, which fans them out to whichever
of ITS OWN locally-connected WebSocket clients care about them.

One instance of this service runs per core-api process, started in
main.py's lifespan (see that module's own comment at the call site) and
stopped gracefully on shutdown via an asyncio.Event, matching the same
lifecycle-management shape RedisBroker.subscribe_and_dispatch() already
expects.

CHANNEL -> TOPIC MAPPING: Redis channel names (channels.py, prefixed
"realtime:") are an internal implementation detail; WebSocket topic
names (documented in realtime_router.py) are the public contract with
frontend clients. This service is the ONE place that translates between
them, so every other publisher only ever needs to know the Redis channel
name it's publishing to, not how that maps to a topic string.
"""

from __future__ import annotations

import asyncio

from observability import get_logger

from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker

logger = get_logger(__name__)

_SUBSCRIBED_CHANNEL_PATTERNS = [
    "realtime:ticker",
    "realtime:quote:*",
    "realtime:watchlist:*",
    "realtime:portfolio:*",
    "realtime:ai:*",
    "realtime:sentiment:*",
    "realtime:alert:*",
]


def _channel_to_topic_and_user(channel: str) -> tuple[str, str | None]:
    """Maps a Redis channel name to (topic, user_id | None). user_id is
    None for market-wide channels (ticker, quote, ai, sentiment) that
    every subscribed connection receives regardless of ownership; it is
    the target user for per-user channels (watchlist, portfolio, alert),
    which are only ever delivered to that specific user's own
    connections."""
    if channel == "realtime:ticker":
        return "ticker", None
    if channel.startswith("realtime:quote:"):
        symbol = channel.removeprefix("realtime:quote:")
        return f"quote:{symbol}", None
    if channel.startswith("realtime:ai:"):
        symbol = channel.removeprefix("realtime:ai:")
        return f"ai:{symbol}", None
    if channel.startswith("realtime:sentiment:"):
        symbol = channel.removeprefix("realtime:sentiment:")
        return f"sentiment:{symbol}", None
    if channel.startswith("realtime:watchlist:"):
        user_id = channel.removeprefix("realtime:watchlist:")
        return "watchlist", user_id
    if channel.startswith("realtime:portfolio:"):
        remainder = channel.removeprefix("realtime:portfolio:")
        user_id, _, portfolio_id = remainder.partition(":")
        return f"portfolio:{portfolio_id}", user_id
    if channel.startswith("realtime:alert:"):
        user_id = channel.removeprefix("realtime:alert:")
        return "alert", user_id
    raise ValueError(f"Unrecognized realtime channel: {channel!r}")


class RealtimeService:
    def __init__(self, connection_manager: ConnectionManager, redis_broker: RedisBroker) -> None:
        self._connection_manager = connection_manager
        self._redis_broker = redis_broker
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._redis_broker.psubscribe_and_dispatch(
                _SUBSCRIBED_CHANNEL_PATTERNS, self._dispatch, stop_event=self._stop_event
            )
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _dispatch(self, channel: str, payload: dict[str, object]) -> None:
        try:
            topic, user_id = _channel_to_topic_and_user(channel)
        except ValueError as exc:
            logger.warning("realtime.dispatch.unrecognized_channel", error=str(exc))
            return

        envelope: dict[str, object] = {"type": topic.split(":")[0], "topic": topic, "data": payload}
        if user_id is None:
            await self._connection_manager.broadcast(envelope, topic=topic)
        else:
            await self._connection_manager.send_to_user(user_id, envelope, topic=topic)
