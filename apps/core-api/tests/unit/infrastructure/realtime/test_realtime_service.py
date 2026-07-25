"""Direct tests for RealtimeService's own dispatch/routing logic —
specifically _channel_to_topic_and_user()'s translation table and
_dispatch()'s broadcast-vs-send_to_user routing decision. Every other
Phase 9 streaming service's tests exercise this indirectly (by
publishing to a channel and trusting delivery happens), but this file
is the first to test RealtimeService's own translation logic directly,
closing a gap identified during task 9's coverage review."""

from __future__ import annotations

import pytest

from src.infrastructure.realtime.realtime_service import (
    RealtimeService,
    _channel_to_topic_and_user,
)


class FakeConnectionManager:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[dict[str, object], str | None]] = []
        self.sends_to_user: list[tuple[str, dict[str, object], str | None]] = []

    async def broadcast(self, message: dict[str, object], *, topic: str | None = None) -> None:
        self.broadcasts.append((message, topic))

    async def send_to_user(
        self, user_id: str, message: dict[str, object], *, topic: str | None = None
    ) -> None:
        self.sends_to_user.append((user_id, message, topic))


class FakeRedisBroker:
    async def psubscribe_and_dispatch(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError  # not exercised by these direct-dispatch tests


class TestChannelToTopicAndUser:
    def test_the_ticker_channel_maps_to_the_ticker_topic_with_no_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:ticker") == ("ticker", None)

    def test_a_quote_channel_maps_to_a_quote_topic_with_no_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:quote:AAPL") == ("quote:AAPL", None)

    def test_an_ai_channel_maps_to_an_ai_topic_with_no_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:ai:AAPL") == ("ai:AAPL", None)

    def test_a_sentiment_channel_maps_to_a_sentiment_topic_with_no_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:sentiment:AAPL") == ("sentiment:AAPL", None)

    def test_a_watchlist_channel_maps_to_the_watchlist_topic_scoped_to_its_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:watchlist:user-1") == ("watchlist", "user-1")

    def test_a_portfolio_channel_maps_to_a_portfolio_topic_scoped_to_its_user(self) -> None:
        result = _channel_to_topic_and_user("realtime:portfolio:user-1:portfolio-9")
        assert result == ("portfolio:portfolio-9", "user-1")

    def test_an_alert_channel_maps_to_the_alert_topic_scoped_to_its_user(self) -> None:
        assert _channel_to_topic_and_user("realtime:alert:user-1") == ("alert", "user-1")

    def test_an_unrecognized_channel_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognized realtime channel"):
            _channel_to_topic_and_user("realtime:something-unknown")


class TestDispatch:
    async def test_a_market_wide_channel_is_broadcast_not_sent_to_a_specific_user(self) -> None:
        connection_manager = FakeConnectionManager()
        service = RealtimeService(connection_manager, FakeRedisBroker())  # type: ignore[arg-type]

        await service._dispatch("realtime:quote:AAPL", {"price": "150"})

        assert len(connection_manager.broadcasts) == 1
        message, topic = connection_manager.broadcasts[0]
        assert topic == "quote:AAPL"
        assert message == {"type": "quote", "topic": "quote:AAPL", "data": {"price": "150"}}
        assert connection_manager.sends_to_user == []

    async def test_a_per_user_channel_is_sent_only_to_its_owning_user(self) -> None:
        connection_manager = FakeConnectionManager()
        service = RealtimeService(connection_manager, FakeRedisBroker())  # type: ignore[arg-type]

        await service._dispatch("realtime:portfolio:user-1:portfolio-9", {"current_value": "1"})

        assert connection_manager.broadcasts == []
        assert len(connection_manager.sends_to_user) == 1
        user_id, message, topic = connection_manager.sends_to_user[0]
        assert user_id == "user-1"
        assert topic == "portfolio:portfolio-9"
        assert message["type"] == "portfolio"

    async def test_an_unrecognized_channel_is_logged_and_does_not_raise(self) -> None:
        connection_manager = FakeConnectionManager()
        service = RealtimeService(connection_manager, FakeRedisBroker())  # type: ignore[arg-type]

        await service._dispatch("realtime:not-a-real-channel", {"whatever": "value"})

        assert connection_manager.broadcasts == []
        assert connection_manager.sends_to_user == []

    async def test_an_alert_channel_dispatch_routes_to_the_correct_user_and_topic(self) -> None:
        connection_manager = FakeConnectionManager()
        service = RealtimeService(connection_manager, FakeRedisBroker())  # type: ignore[arg-type]

        await service._dispatch("realtime:alert:user-42", {"title": "Alert triggered"})

        assert len(connection_manager.sends_to_user) == 1
        user_id, message, topic = connection_manager.sends_to_user[0]
        assert user_id == "user-42"
        assert topic == "alert"
        assert message["type"] == "alert"
