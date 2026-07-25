"""ListNotificationsUseCase, MarkNotificationAsReadUseCase,
MarkAllNotificationsAsReadUseCase."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.notifications.ownership import get_owned_notification_or_raise
from src.domain.notifications.entities import Notification
from src.domain.notifications.repositories import (
    NotificationListFilter,
    NotificationPageResult,
    NotificationRepository,
)
from src.domain.notifications.value_objects import NotificationId


@dataclass(frozen=True, slots=True)
class ListNotificationsQuery:
    user_id: str
    unread_only: bool = False
    page: int = 1
    page_size: int = 20


class ListNotificationsUseCase:
    def __init__(self, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(self, query: ListNotificationsQuery) -> NotificationPageResult:
        filters = NotificationListFilter(
            unread_only=query.unread_only, page=query.page, page_size=query.page_size
        )
        return await self._notification_repository.list_for_user(query.user_id, filters)


class MarkNotificationAsReadUseCase:
    def __init__(self, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(
        self, notification_id: NotificationId, requesting_user_id: str
    ) -> Notification:
        notification = await get_owned_notification_or_raise(
            self._notification_repository, notification_id, requesting_user_id
        )
        notification.mark_as_read()
        await self._notification_repository.save(notification)
        return notification


class MarkAllNotificationsAsReadUseCase:
    def __init__(self, notification_repository: NotificationRepository) -> None:
        self._notification_repository = notification_repository

    async def execute(self, user_id: str) -> int:
        """Returns the number of notifications marked as read — backs
        POST /notifications/read-all, matching
        NotificationRepository.mark_all_as_read_for_user()'s bulk-update
        contract (no per-row entity loading required)."""
        return await self._notification_repository.mark_all_as_read_for_user(user_id)
