"""Shared ownership-enforcement helper for notification use cases.

Document 3 §7.5's resource-level ownership rule, applied consistently
across every use case that operates on a specific notification_id —
mirrors src.application.alerts.ownership's role for the alerts context.
"""

from __future__ import annotations

from src.domain.notifications.entities import Notification
from src.domain.notifications.exceptions import (
    NotificationNotFoundError,
    NotificationOwnershipError,
)
from src.domain.notifications.repositories import NotificationRepository
from src.domain.notifications.value_objects import NotificationId


async def get_owned_notification_or_raise(
    notification_repository: NotificationRepository,
    notification_id: NotificationId,
    requesting_user_id: str,
) -> Notification:
    notification = await notification_repository.get_by_id(notification_id)
    if notification is None:
        raise NotificationNotFoundError(f"No notification with id {notification_id}")
    if notification.user_id != requesting_user_id:
        raise NotificationOwnershipError(
            f"User {requesting_user_id} does not own notification {notification_id}"
        )
    return notification
