"""Domain <-> ORM mapping functions for the notifications bounded context.

Mirrors alert_mappers.py's pattern — pure functions, no side effects,
isolate the domain layer from SQLAlchemy model shape. Two mapper pairs
exist here, matching the two entities (Notification,
NotificationPreferences) and their two underlying tables.
"""

from __future__ import annotations

from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.value_objects import NotificationId
from src.infrastructure.persistence.postgres.alert_models import (
    NotificationModel,
    NotificationPreferenceModel,
)


def notification_to_domain(model: NotificationModel) -> Notification:
    return Notification(
        id=NotificationId(model.id),
        user_id=str(model.user_id),
        type=model.type,  # type: ignore[arg-type]  # application-controlled column, always a valid NotificationType
        title=model.title,
        body=model.body,
        metadata=dict(model.metadata_),
        read_at=model.read_at,
        created_at=model.created_at,
    )


def notification_to_model(
    notification: Notification, existing: NotificationModel | None
) -> NotificationModel:
    model = existing if existing is not None else NotificationModel(id=notification.id.value)
    model.user_id = notification.user_id  # type: ignore[assignment]  # str -> UUID column, driver-coerced
    model.type = notification.type
    model.title = notification.title
    model.body = notification.body
    model.metadata_ = notification.metadata
    model.read_at = notification.read_at
    model.created_at = notification.created_at
    return model


def notification_preferences_to_domain(
    model: NotificationPreferenceModel,
) -> NotificationPreferences:
    return NotificationPreferences(
        user_id=str(model.user_id),
        price_alerts_email=model.price_alerts_email,
        price_alerts_push=model.price_alerts_push,
        digest_frequency=model.digest_frequency,  # type: ignore[arg-type]  # DB CHECK constraint guarantees a valid DigestFrequency
        quiet_hours_start=model.quiet_hours_start,
        quiet_hours_end=model.quiet_hours_end,
    )


def notification_preferences_to_model(
    preferences: NotificationPreferences, existing: NotificationPreferenceModel | None
) -> NotificationPreferenceModel:
    model = (
        existing
        if existing is not None
        else NotificationPreferenceModel(user_id=preferences.user_id)
    )
    model.price_alerts_email = preferences.price_alerts_email
    model.price_alerts_push = preferences.price_alerts_push
    model.digest_frequency = preferences.digest_frequency
    model.quiet_hours_start = preferences.quiet_hours_start
    model.quiet_hours_end = preferences.quiet_hours_end
    return model
