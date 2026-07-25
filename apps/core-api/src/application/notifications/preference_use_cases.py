"""GetNotificationPreferencesUseCase, UpdateNotificationPreferencesUseCase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from src.domain.notifications.entities import DigestFrequency, NotificationPreferences
from src.domain.notifications.repositories import NotificationPreferenceRepository


class GetNotificationPreferencesUseCase:
    def __init__(self, preference_repository: NotificationPreferenceRepository) -> None:
        self._preference_repository = preference_repository

    async def execute(self, user_id: str) -> NotificationPreferences:
        """Returns the user's stored preferences, or an in-memory default
        (matching the DB columns' own server_default values) if the user
        has no notification_preferences row yet — so this endpoint never
        404s for a user who simply hasn't customized their preferences."""
        preferences = await self._preference_repository.get_by_user_id(user_id)
        if preferences is None:
            return NotificationPreferences.create_default(user_id)
        return preferences


@dataclass(frozen=True, slots=True)
class UpdateNotificationPreferencesCommand:
    user_id: str
    price_alerts_email: bool | None = None
    price_alerts_push: bool | None = None
    digest_frequency: DigestFrequency | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    clear_quiet_hours: bool = False


class UpdateNotificationPreferencesUseCase:
    def __init__(self, preference_repository: NotificationPreferenceRepository) -> None:
        self._preference_repository = preference_repository

    async def execute(
        self, command: UpdateNotificationPreferencesCommand
    ) -> NotificationPreferences:
        preferences = await self._preference_repository.get_by_user_id(command.user_id)
        if preferences is None:
            preferences = NotificationPreferences.create_default(command.user_id)

        preferences.update(
            price_alerts_email=command.price_alerts_email,
            price_alerts_push=command.price_alerts_push,
            digest_frequency=command.digest_frequency,
            quiet_hours_start=command.quiet_hours_start,
            quiet_hours_end=command.quiet_hours_end,
            clear_quiet_hours=command.clear_quiet_hours,
        )
        await self._preference_repository.save(preferences)
        return preferences
