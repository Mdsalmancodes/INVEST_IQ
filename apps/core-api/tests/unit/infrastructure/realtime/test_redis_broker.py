"""Tests for RedisBroker — a fake Redis double implementing just the
publish()/pubsub() surface RedisBroker actually calls, no real Redis
connection needed. Matches the codebase's established "small
purpose-built fake, not a new dependency" convention (e.g.
test_token_blacklist.py's FakeRedis).
"""

from __future__ import annotations

import asyncio
import json

from redis.exceptions import RedisError

from src.infrastructure.realtime.redis_broker import RedisBroker


class FakePubSub:
    def __init__(self, messages: list[dict[str, object]] | None = None) -> None:
        self.subscribed_channels: list[str] = []
        self.psubscribed_patterns: list[str] = []
        self.unsubscribed = False
        self.punsubscribed = False
        self.closed = False
        self._messages = list(messages or [])

    async def subscribe(self, *channels: str) -> None:
        self.subscribed_channels.extend(channels)

    async def psubscribe(self, *patterns: str) -> None:
        self.psubscribed_patterns.extend(patterns)

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed = True

    async def punsubscribe(self, *patterns: str) -> None:
        self.punsubscribed = True

    async def get_message(
        self, ignore_subscribe_messages: bool = True, timeout: float = 1.0
    ) -> dict[str, object] | None:
        if self._messages:
            return self._messages.pop(0)
        # Real Redis's get_message(timeout=...) blocks for up to `timeout`
        # seconds before returning None when no message is pending. This
        # fake must yield control for a non-zero (if tiny) duration too —
        # returning None immediately turns _pump's `while not
        # stop_event.is_set()` loop into a zero-delay busy-spin that can
        # starve the sibling `run_briefly()` task of scheduling time under
        # some event-loop implementations, hanging the test indefinitely
        # rather than genuinely running fast. A 1ms sleep is enough to
        # cooperatively yield without meaningfully slowing the test down.
        await asyncio.sleep(0.001)
        return None

    async def aclose(self) -> None:
        self.closed = True


class FakeRedis:
    def __init__(self, pubsub_double: FakePubSub | None = None) -> None:
        self.published: list[tuple[str, str]] = []
        self._pubsub_double = pubsub_double or FakePubSub()
        self.publish_raises = False

    async def publish(self, channel: str, payload: str) -> None:
        if self.publish_raises:
            raise RedisError("connection refused")
        self.published.append((channel, payload))

    def pubsub(self) -> FakePubSub:
        return self._pubsub_double


class TestPublish:
    async def test_publishes_the_payload_as_json(self) -> None:
        redis = FakeRedis()
        broker = RedisBroker(redis)  # type: ignore[arg-type]

        await broker.publish("realtime:quote:AAPL", {"price": "150.00"})

        assert len(redis.published) == 1
        channel, payload = redis.published[0]
        assert channel == "realtime:quote:AAPL"
        assert json.loads(payload) == {"price": "150.00"}

    async def test_a_redis_error_is_logged_not_raised(self) -> None:
        redis = FakeRedis()
        redis.publish_raises = True
        broker = RedisBroker(redis)  # type: ignore[arg-type]

        # Must not raise — fail-open, matching RateLimitMiddleware's
        # Phase 8 precedent for best-effort infrastructure dependencies.
        await broker.publish("realtime:quote:AAPL", {"price": "150.00"})


class TestSubscribeAndDispatch:
    async def test_dispatches_each_received_message_to_the_handler(self) -> None:
        pubsub = FakePubSub(
            messages=[
                {"channel": "realtime:ticker", "data": json.dumps({"nifty": 100})},
            ]
        )
        redis = FakeRedis(pubsub_double=pubsub)
        broker = RedisBroker(redis)  # type: ignore[arg-type]
        received: list[tuple[str, dict[str, object]]] = []

        async def handler(channel: str, payload: dict[str, object]) -> None:
            received.append((channel, payload))

        stop_event = asyncio.Event()

        async def run_briefly() -> None:
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.wait_for(
            asyncio.gather(
                broker.subscribe_and_dispatch(
                    ["realtime:ticker"], handler, stop_event=stop_event
                ),
                run_briefly(),
            ),
            timeout=5.0,
        )

        assert received == [("realtime:ticker", {"nifty": 100})]
        assert pubsub.subscribed_channels == ["realtime:ticker"]
        assert pubsub.unsubscribed is True
        assert pubsub.closed is True

    async def test_a_malformed_payload_is_skipped_not_raised(self) -> None:
        pubsub = FakePubSub(messages=[{"channel": "realtime:ticker", "data": "not-json"}])
        redis = FakeRedis(pubsub_double=pubsub)
        broker = RedisBroker(redis)  # type: ignore[arg-type]
        received: list[object] = []

        async def handler(channel: str, payload: dict[str, object]) -> None:
            received.append(payload)

        stop_event = asyncio.Event()

        async def run_briefly() -> None:
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.wait_for(
            asyncio.gather(
                broker.subscribe_and_dispatch(
                    ["realtime:ticker"], handler, stop_event=stop_event
                ),
                run_briefly(),
            ),
            timeout=5.0,
        )

        assert received == []


class TestPsubscribeAndDispatch:
    async def test_dispatches_pattern_matched_messages_with_the_concrete_channel_name(
        self,
    ) -> None:
        pubsub = FakePubSub(
            messages=[{"channel": "realtime:quote:AAPL", "data": json.dumps({"price": "1"})}]
        )
        redis = FakeRedis(pubsub_double=pubsub)
        broker = RedisBroker(redis)  # type: ignore[arg-type]
        received: list[tuple[str, dict[str, object]]] = []

        async def handler(channel: str, payload: dict[str, object]) -> None:
            received.append((channel, payload))

        stop_event = asyncio.Event()

        async def run_briefly() -> None:
            await asyncio.sleep(0.05)
            stop_event.set()

        await asyncio.wait_for(
            asyncio.gather(
                broker.psubscribe_and_dispatch(
                    ["realtime:quote:*"], handler, stop_event=stop_event
                ),
                run_briefly(),
            ),
            timeout=5.0,
        )

        assert received == [("realtime:quote:AAPL", {"price": "1"})]
        assert pubsub.psubscribed_patterns == ["realtime:quote:*"]
        assert pubsub.punsubscribed is True
