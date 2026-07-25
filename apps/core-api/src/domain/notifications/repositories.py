"""Repository interfaces (Protocols) for the notifications bounded context.

Per docs/architecture/02-clean-architecture-folder-frontend.md §4.1: these
live in the domain layer and are implemented by infrastructure — the
dependency arrow always points inward. Two Protocols exist here, matching
the two entities (Notification, NotificationPreferences) and their two
underlying tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.value_objects import NotificationId


@dataclass(frozen=True, slots=True)
class NotificationListFilter:
    """Filter/pagination parameters for ListNotifications — matches
    Alert's AlertListFilter pattern (plain domain-layer dataclass, not
    Pydantic, which belongs to the presentation layer)."""

    unread_only: bool = False
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True, slots=True)
class NotificationPageResult:
    items: tuple[Notification, ...]
    total_count: int
    unread_count: int
    page: int
    page_size: int


class NotificationRepository(Protocol):
    async def save(self, notification: Notification) -> None:
        """Insert or update the Notification row — upsert semantics,
        matching Alert/WatchlistRepository.save() convention. In practice
        only ever inserts (create) or updates read_at (mark_as_read)."""
        ...

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None: ...

    async def list_for_user(
        self, user_id: str, filters: NotificationListFilter
    ) -> NotificationPageResult: ...

    async def mark_all_as_read_for_user(self, user_id: str) -> int:
        """Bulk mark-as-read, returning the number of rows affected —
        backs POST /notifications/read-all without requiring the
        application layer to load every Notification into memory first."""
        ...


class NotificationPreferenceRepository(Protocol):
    async def save(self, preferences: NotificationPreferences) -> None:
        """Insert or update the NotificationPreference row — upsert
        semantics, since user_id is the primary key (1:1 with User)."""
        ...

    async def get_by_user_id(self, user_id: str) -> NotificationPreferences | None: ...
