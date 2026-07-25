"""UpdateAlertUseCase — updates condition/threshold/recurrence/cooldown
and/or active state on a single alert.

Backs a single PATCH /alerts/{id} endpoint that exposes all mutable
fields together — matches UpdateWatchlistUseCase's combined rename+
set-default shape (one endpoint, several optional fields, all applied in
one save()).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.alerts.ownership import get_owned_alert_or_raise
from src.domain.alerts.entities import Alert, ConditionType
from src.domain.alerts.repositories import AlertRepository
from src.domain.alerts.value_objects import AlertId


@dataclass(frozen=True, slots=True)
class UpdateAlertCommand:
    alert_id: AlertId
    requesting_user_id: str
    condition_type: ConditionType | None = None
    threshold: Decimal | None = None
    is_recurring: bool | None = None
    cooldown_minutes: int | None = None
    is_active: bool | None = None


class UpdateAlertUseCase:
    def __init__(self, alert_repository: AlertRepository) -> None:
        self._alert_repository = alert_repository

    async def execute(self, command: UpdateAlertCommand) -> Alert:
        alert = await get_owned_alert_or_raise(
            self._alert_repository, command.alert_id, command.requesting_user_id
        )

        alert.update_condition(
            condition_type=command.condition_type,
            threshold=command.threshold,
            is_recurring=command.is_recurring,
            cooldown_minutes=command.cooldown_minutes,
        )

        if command.is_active is True:
            alert.reactivate()
        elif command.is_active is False:
            alert.deactivate()

        await self._alert_repository.save(alert)
        return alert
