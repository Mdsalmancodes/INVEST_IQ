"""SubscriptionRegistry — per-connection state tracking which topics a
single WebSocket connection has subscribed to.

One instance per WebSocket connection (created fresh in realtime_router's
handler, not shared) — deliberately NOT part of ConnectionManager's own
state, since ConnectionManager's job is connection lifecycle (which
sockets exist for a user), while this is per-socket subscription intent
(which of THAT socket's topics it cares about). Two tabs for the same
user might subscribe to different symbols; keeping this per-connection
rather than per-user is what makes that correct.

Topic strings are free-form and match the ones documented in
realtime_router.py's module docstring (e.g. "quote:AAPL",
"portfolio:<id>", "ai:AAPL") — this registry does not validate or
interpret them, it is a pure set of strings the dispatch layer
(realtime_service.py) checks membership against before delivering a
message to this specific connection.
"""

from __future__ import annotations

from collections.abc import Iterable


class SubscriptionRegistry:
    def __init__(self) -> None:
        self._topics: set[str] = set()

    def subscribe(self, topics: Iterable[str]) -> None:
        self._topics.update(topics)

    def unsubscribe(self, topics: Iterable[str]) -> None:
        self._topics.difference_update(topics)

    def is_subscribed(self, topic: str) -> bool:
        return topic in self._topics

    def topics(self) -> frozenset[str]:
        return frozenset(self._topics)
