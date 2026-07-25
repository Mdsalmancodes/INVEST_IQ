from __future__ import annotations

from src.infrastructure.realtime.subscription_registry import SubscriptionRegistry


class TestSubscriptionRegistry:
    def test_starts_with_no_subscriptions(self) -> None:
        registry = SubscriptionRegistry()
        assert registry.topics() == frozenset()
        assert registry.is_subscribed("quote:AAPL") is False

    def test_subscribe_adds_topics(self) -> None:
        registry = SubscriptionRegistry()
        registry.subscribe(["quote:AAPL", "quote:MSFT"])
        assert registry.is_subscribed("quote:AAPL") is True
        assert registry.is_subscribed("quote:MSFT") is True
        assert registry.is_subscribed("quote:GOOG") is False

    def test_subscribing_to_an_already_subscribed_topic_is_idempotent(self) -> None:
        registry = SubscriptionRegistry()
        registry.subscribe(["quote:AAPL"])
        registry.subscribe(["quote:AAPL"])
        assert registry.topics() == frozenset({"quote:AAPL"})

    def test_unsubscribe_removes_a_topic(self) -> None:
        registry = SubscriptionRegistry()
        registry.subscribe(["quote:AAPL", "quote:MSFT"])
        registry.unsubscribe(["quote:AAPL"])
        assert registry.is_subscribed("quote:AAPL") is False
        assert registry.is_subscribed("quote:MSFT") is True

    def test_unsubscribing_a_never_subscribed_topic_does_not_raise(self) -> None:
        registry = SubscriptionRegistry()
        registry.unsubscribe(["quote:AAPL"])
        assert registry.topics() == frozenset()
