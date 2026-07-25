"""SqlAlchemyNotificationPreferenceRepository — implements
src.domain.notifications.repositories.NotificationPreferenceRepository."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.notifications.entities import NotificationPreferences
from src.infrastructure.persistence.postgres.alert_models import NotificationPreferenceModel
from src.infrastructure.persistence.postgres.repositories.notification_mappers import (
    notification_preferences_to_domain,
    notification_preferences_to_model,
)


class SqlAlchemyNotificationPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, preferences: NotificationPreferences) -> None:
        existing = await self._session.get(
            NotificationPreferenceModel, uuid.UUID(preferences.user_id)
        )
        model = notification_preferences_to_model(preferences, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def get_by_user_id(self, user_id: str) -> NotificationPreferences | None:
        model = await self._session.get(NotificationPreferenceModel, uuid.UUID(user_id))
        return notification_preferences_to_domain(model) if model is not None else None
