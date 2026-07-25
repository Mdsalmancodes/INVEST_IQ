"""Dependency-injection wiring for notification use cases — mirrors
src.presentation.dependencies.alert_use_cases's pattern.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.notifications.notification_use_cases import (
    ListNotificationsUseCase,
    MarkAllNotificationsAsReadUseCase,
    MarkNotificationAsReadUseCase,
)
from src.application.notifications.preference_use_cases import (
    GetNotificationPreferencesUseCase,
    UpdateNotificationPreferencesUseCase,
)
from src.infrastructure.persistence.postgres.repositories.notification_preference_repository import (  # noqa: E501
    SqlAlchemyNotificationPreferenceRepository,
)
from src.infrastructure.persistence.postgres.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
)
from src.infrastructure.persistence.postgres.session import get_db_session


def get_list_notifications_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ListNotificationsUseCase:
    return ListNotificationsUseCase(SqlAlchemyNotificationRepository(session))


def get_mark_notification_as_read_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MarkNotificationAsReadUseCase:
    return MarkNotificationAsReadUseCase(SqlAlchemyNotificationRepository(session))


def get_mark_all_notifications_as_read_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MarkAllNotificationsAsReadUseCase:
    return MarkAllNotificationsAsReadUseCase(SqlAlchemyNotificationRepository(session))


def get_get_notification_preferences_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GetNotificationPreferencesUseCase:
    return GetNotificationPreferencesUseCase(SqlAlchemyNotificationPreferenceRepository(session))


def get_update_notification_preferences_use_case(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdateNotificationPreferencesUseCase:
    return UpdateNotificationPreferencesUseCase(
        SqlAlchemyNotificationPreferenceRepository(session)
    )
