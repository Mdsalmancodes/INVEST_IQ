"""Unit tests for the Phase 6 notification application-layer use cases —
ListNotifications, MarkNotificationAsRead, MarkAllNotificationsAsRead,
GetNotificationPreferences, UpdateNotificationPreferences."""

from __future__ import annotations

import pytest

from src.application.notifications.notification_use_cases import (
    ListNotificationsQuery,
    ListNotificationsUseCase,
    MarkAllNotificationsAsReadUseCase,
    MarkNotificationAsReadUseCase,
)
from src.application.notifications.preference_use_cases import (
    GetNotificationPreferencesUseCase,
    UpdateNotificationPreferencesCommand,
    UpdateNotificationPreferencesUseCase,
)
from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.exceptions import (
    NotificationNotFoundError,
    NotificationOwnershipError,
)
from src.domain.notifications.repositories import NotificationListFilter, NotificationPageResult
from src.domain.notifications.value_objects import NotificationId


class FakeNotificationRepository:
    def __init__(self) -> None:
        self._store: dict[str, Notification] = {}

    async def save(self, notification: Notification) -> None:
        self._store[str(notification.id)] = notification

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        return self._store.get(str(notification_id))

    async def list_for_user(
        self, user_id: str, filters: NotificationListFilter
    ) -> NotificationPageResult:
        matching = [n for n in self._store.values() if n.user_id == user_id]
        unread_count = sum(1 for n in matching if not n.is_read)
        if filters.unread_only:
            matching = [n for n in matching if not n.is_read]
        matching.sort(key=lambda n: n.created_at, reverse=True)
        return NotificationPageResult(
            items=tuple(matching),
            total_count=len(matching),
            unread_count=unread_count,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def mark_all_as_read_for_user(self, user_id: str) -> int:
        count = 0
        for notification in self._store.values():
            if notification.user_id == user_id and not notification.is_read:
                notification.mark_as_read()
                count += 1
        return count


class FakeNotificationPreferenceRepository:
    def __init__(self) -> None:
        self._store: dict[str, NotificationPreferences] = {}

    async def save(self, preferences: NotificationPreferences) -> None:
        self._store[preferences.user_id] = preferences

    async def get_by_user_id(self, user_id: str) -> NotificationPreferences | None:
        return self._store.get(user_id)


class TestListNotificationsUseCase:
    async def test_lists_only_the_requesting_users_notifications(self) -> None:
        repo = FakeNotificationRepository()
        await repo.save(Notification.create(user_id="user-1", type="system", title="A", body="a"))
        await repo.save(Notification.create(user_id="user-2", type="system", title="B", body="b"))

        result = await ListNotificationsUseCase(repo).execute(
            ListNotificationsQuery(user_id="user-1")
        )

        assert result.total_count == 1
        assert result.items[0].user_id == "user-1"

    async def test_unread_only_filters_read_notifications(self) -> None:
        repo = FakeNotificationRepository()
        unread = Notification.create(user_id="user-1", type="system", title="Unread", body="u")
        read = Notification.create(user_id="user-1", type="system", title="Read", body="r")
        read.mark_as_read()
        await repo.save(unread)
        await repo.save(read)

        result = await ListNotificationsUseCase(repo).execute(
            ListNotificationsQuery(user_id="user-1", unread_only=True)
        )

        assert result.total_count == 1
        assert result.items[0].id == unread.id

    async def test_unread_count_reflects_all_matching_notifications_regardless_of_filter(
        self,
    ) -> None:
        repo = FakeNotificationRepository()
        unread = Notification.create(user_id="user-1", type="system", title="Unread", body="u")
        read = Notification.create(user_id="user-1", type="system", title="Read", body="r")
        read.mark_as_read()
        await repo.save(unread)
        await repo.save(read)

        result = await ListNotificationsUseCase(repo).execute(
            ListNotificationsQuery(user_id="user-1", unread_only=False)
        )

        assert result.total_count == 2
        assert result.unread_count == 1


class TestMarkNotificationAsReadUseCase:
    async def test_marks_owned_notification_as_read(self) -> None:
        repo = FakeNotificationRepository()
        notification = Notification.create(
            user_id="user-1", type="system", title="Welcome", body="body"
        )
        await repo.save(notification)

        result = await MarkNotificationAsReadUseCase(repo).execute(notification.id, "user-1")

        assert result.is_read is True

    async def test_raises_not_found_for_unknown_id(self) -> None:
        repo = FakeNotificationRepository()
        with pytest.raises(NotificationNotFoundError):
            await MarkNotificationAsReadUseCase(repo).execute(NotificationId.new(), "user-1")

    async def test_raises_ownership_error_for_other_users_notification(self) -> None:
        repo = FakeNotificationRepository()
        notification = Notification.create(
            user_id="user-1", type="system", title="Welcome", body="body"
        )
        await repo.save(notification)

        with pytest.raises(NotificationOwnershipError):
            await MarkNotificationAsReadUseCase(repo).execute(notification.id, "user-2")


class TestMarkAllNotificationsAsReadUseCase:
    async def test_marks_all_unread_notifications_for_user(self) -> None:
        repo = FakeNotificationRepository()
        await repo.save(Notification.create(user_id="user-1", type="system", title="A", body="a"))
        await repo.save(Notification.create(user_id="user-1", type="system", title="B", body="b"))
        await repo.save(Notification.create(user_id="user-2", type="system", title="C", body="c"))

        count = await MarkAllNotificationsAsReadUseCase(repo).execute("user-1")

        assert count == 2
        result = await repo.list_for_user(
            "user-1", NotificationListFilter(unread_only=True, page=1, page_size=20)
        )
        assert result.total_count == 0

    async def test_returns_zero_when_nothing_to_mark(self) -> None:
        repo = FakeNotificationRepository()
        count = await MarkAllNotificationsAsReadUseCase(repo).execute("user-1")
        assert count == 0


class TestGetNotificationPreferencesUseCase:
    async def test_returns_default_when_none_stored(self) -> None:
        repo = FakeNotificationPreferenceRepository()
        prefs = await GetNotificationPreferencesUseCase(repo).execute("user-1")
        assert prefs.digest_frequency == "daily"
        assert prefs.price_alerts_email is True

    async def test_returns_stored_preferences_when_present(self) -> None:
        repo = FakeNotificationPreferenceRepository()
        stored = NotificationPreferences.create_default("user-1")
        stored.update(digest_frequency="weekly")
        await repo.save(stored)

        prefs = await GetNotificationPreferencesUseCase(repo).execute("user-1")

        assert prefs.digest_frequency == "weekly"


class TestUpdateNotificationPreferencesUseCase:
    async def test_creates_and_updates_when_none_stored(self) -> None:
        repo = FakeNotificationPreferenceRepository()

        prefs = await UpdateNotificationPreferencesUseCase(repo).execute(
            UpdateNotificationPreferencesCommand(user_id="user-1", digest_frequency="off")
        )

        assert prefs.digest_frequency == "off"
        stored = await repo.get_by_user_id("user-1")
        assert stored is not None
        assert stored.digest_frequency == "off"

    async def test_updates_existing_preferences(self) -> None:
        repo = FakeNotificationPreferenceRepository()
        await repo.save(NotificationPreferences.create_default("user-1"))

        prefs = await UpdateNotificationPreferencesUseCase(repo).execute(
            UpdateNotificationPreferencesCommand(user_id="user-1", price_alerts_push=False)
        )

        assert prefs.price_alerts_push is False
        assert prefs.price_alerts_email is True
