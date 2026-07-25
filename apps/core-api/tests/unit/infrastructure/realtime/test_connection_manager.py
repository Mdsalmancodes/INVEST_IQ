"""Tests for ConnectionManager — a pure in-memory registry, directly
unit-testable with a minimal fake WebSocket (no real network/ASGI
server needed; that tier is covered by test_realtime_router.py instead).
"""

from __future__ import annotations

from src.infrastructure.realtime.connection_manager import ConnectionManager


class FakeWebSocket:
    """Minimal double satisfying the two methods ConnectionManager calls:
    accept() (during connect) and send_json() (during delivery). Records
    every sent message so tests can assert on exactly what was delivered.
    """

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent_messages: list[dict[str, object]] = []
        self._fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, object]) -> None:
        if self._fail_on_send:
            raise RuntimeError("connection is dead")
        self.sent_messages.append(message)


class TestConnectAndDisconnect:
    async def test_connect_accepts_the_socket_and_returns_a_subscription_registry(self) -> None:
        manager = ConnectionManager()
        ws = FakeWebSocket()

        subscriptions = await manager.connect("user-1", ws)  # type: ignore[arg-type]

        assert ws.accepted is True
        assert manager.connection_count_for_user("user-1") == 1
        assert subscriptions.topics() == frozenset()

    async def test_a_user_can_have_multiple_simultaneous_connections(self) -> None:
        manager = ConnectionManager()
        ws_tab_one = FakeWebSocket()
        ws_tab_two = FakeWebSocket()

        await manager.connect("user-1", ws_tab_one)  # type: ignore[arg-type]
        await manager.connect("user-1", ws_tab_two)  # type: ignore[arg-type]

        assert manager.connection_count_for_user("user-1") == 2
        assert manager.total_connection_count() == 2

    async def test_disconnect_removes_only_the_given_connection(self) -> None:
        manager = ConnectionManager()
        ws_tab_one = FakeWebSocket()
        ws_tab_two = FakeWebSocket()
        await manager.connect("user-1", ws_tab_one)  # type: ignore[arg-type]
        await manager.connect("user-1", ws_tab_two)  # type: ignore[arg-type]

        await manager.disconnect("user-1", ws_tab_one)  # type: ignore[arg-type]

        assert manager.connection_count_for_user("user-1") == 1

    async def test_disconnecting_the_last_connection_removes_the_user_entirely(self) -> None:
        manager = ConnectionManager()
        ws = FakeWebSocket()
        await manager.connect("user-1", ws)  # type: ignore[arg-type]

        await manager.disconnect("user-1", ws)  # type: ignore[arg-type]

        assert manager.connection_count_for_user("user-1") == 0
        assert "user-1" not in manager.connected_user_ids()

    async def test_disconnecting_an_unknown_user_is_a_no_op(self) -> None:
        manager = ConnectionManager()
        await manager.disconnect("never-connected", FakeWebSocket())  # type: ignore[arg-type]
        assert manager.total_connection_count() == 0


class TestAllSubscribedTopics:
    async def test_collects_topics_across_every_connection_and_user(self) -> None:
        manager = ConnectionManager()
        subs_one = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subs_two = await manager.connect("user-2", FakeWebSocket())  # type: ignore[arg-type]
        subs_one.subscribe(["quote:AAPL"])
        subs_two.subscribe(["quote:MSFT", "portfolio:abc"])

        assert manager.all_subscribed_topics() == frozenset(
            {"quote:AAPL", "quote:MSFT", "portfolio:abc"}
        )

    async def test_returns_empty_frozenset_when_no_connections_exist(self) -> None:
        manager = ConnectionManager()
        assert manager.all_subscribed_topics() == frozenset()


class TestUserIdsSubscribedTo:
    async def test_returns_users_with_at_least_one_matching_connection(self) -> None:
        manager = ConnectionManager()
        subs_one = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        await manager.connect("user-2", FakeWebSocket())  # type: ignore[arg-type]
        subs_one.subscribe(["watchlist"])

        assert manager.user_ids_subscribed_to("watchlist") == frozenset({"user-1"})

    async def test_a_user_with_multiple_connections_counts_if_any_one_is_subscribed(self) -> None:
        manager = ConnectionManager()
        await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subs_tab_two = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subs_tab_two.subscribe(["watchlist"])

        assert manager.user_ids_subscribed_to("watchlist") == frozenset({"user-1"})

    async def test_returns_empty_frozenset_when_nobody_is_subscribed(self) -> None:
        manager = ConnectionManager()
        await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]

        assert manager.user_ids_subscribed_to("watchlist") == frozenset()

    async def test_matches_by_prefix_for_portfolio_scoped_topics(self) -> None:
        manager = ConnectionManager()
        subs = await manager.connect("user-1", FakeWebSocket())  # type: ignore[arg-type]
        subs.subscribe(["portfolio:abc-123"])

        assert manager.user_ids_subscribed_to("portfolio:") == frozenset({"user-1"})


class TestSendToUser:
    async def test_delivers_to_every_connection_for_that_user_when_no_topic_filter_given(
        self,
    ) -> None:
        manager = ConnectionManager()
        ws_one = FakeWebSocket()
        ws_two = FakeWebSocket()
        await manager.connect("user-1", ws_one)  # type: ignore[arg-type]
        await manager.connect("user-1", ws_two)  # type: ignore[arg-type]

        await manager.send_to_user("user-1", {"type": "alert", "data": {}})

        assert ws_one.sent_messages == [{"type": "alert", "data": {}}]
        assert ws_two.sent_messages == [{"type": "alert", "data": {}}]

    async def test_is_a_no_op_for_a_user_with_no_connections(self) -> None:
        manager = ConnectionManager()
        # Must not raise even though "ghost-user" was never connected.
        await manager.send_to_user("ghost-user", {"type": "alert"})

    async def test_topic_filter_only_delivers_to_subscribed_connections(self) -> None:
        manager = ConnectionManager()
        ws_subscribed = FakeWebSocket()
        ws_unsubscribed = FakeWebSocket()
        subs_subscribed = await manager.connect("user-1", ws_subscribed)  # type: ignore[arg-type]
        await manager.connect("user-1", ws_unsubscribed)  # type: ignore[arg-type]
        subs_subscribed.subscribe(["portfolio:abc"])

        await manager.send_to_user(
            "user-1", {"type": "portfolio", "data": {}}, topic="portfolio:abc"
        )

        assert ws_subscribed.sent_messages == [{"type": "portfolio", "data": {}}]
        assert ws_unsubscribed.sent_messages == []

    async def test_a_failed_send_disconnects_only_that_connection_not_others(self) -> None:
        manager = ConnectionManager()
        ws_healthy = FakeWebSocket()
        ws_dead = FakeWebSocket(fail_on_send=True)
        await manager.connect("user-1", ws_healthy)  # type: ignore[arg-type]
        await manager.connect("user-1", ws_dead)  # type: ignore[arg-type]

        await manager.send_to_user("user-1", {"type": "alert"})

        assert ws_healthy.sent_messages == [{"type": "alert"}]
        assert manager.connection_count_for_user("user-1") == 1


class TestBroadcast:
    async def test_delivers_to_every_connected_user(self) -> None:
        manager = ConnectionManager()
        ws_user_one = FakeWebSocket()
        ws_user_two = FakeWebSocket()
        await manager.connect("user-1", ws_user_one)  # type: ignore[arg-type]
        await manager.connect("user-2", ws_user_two)  # type: ignore[arg-type]

        await manager.broadcast({"type": "ticker", "data": {}})

        assert ws_user_one.sent_messages == [{"type": "ticker", "data": {}}]
        assert ws_user_two.sent_messages == [{"type": "ticker", "data": {}}]

    async def test_topic_filter_applies_per_connection_across_all_users(self) -> None:
        manager = ConnectionManager()
        ws_subscribed = FakeWebSocket()
        ws_unsubscribed = FakeWebSocket()
        subs = await manager.connect("user-1", ws_subscribed)  # type: ignore[arg-type]
        await manager.connect("user-2", ws_unsubscribed)  # type: ignore[arg-type]
        subs.subscribe(["quote:AAPL"])

        await manager.broadcast({"type": "quote", "data": {}}, topic="quote:AAPL")

        assert ws_subscribed.sent_messages == [{"type": "quote", "data": {}}]
        assert ws_unsubscribed.sent_messages == []

    async def test_is_a_no_op_when_no_connections_exist(self) -> None:
        manager = ConnectionManager()
        await manager.broadcast({"type": "ticker"})
        assert manager.total_connection_count() == 0
