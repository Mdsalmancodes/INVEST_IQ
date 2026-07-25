"""Shared ownership-enforcement helper for alert use cases.

Document 3 §7.5's resource-level ownership rule, applied consistently
across every use case that operates on a specific alert_id — mirrors
src.application.watchlist.ownership's role for the watchlist context.
"""

from __future__ import annotations

from src.domain.alerts.entities import Alert
from src.domain.alerts.exceptions import AlertNotFoundError, AlertOwnershipError
from src.domain.alerts.repositories import AlertRepository
from src.domain.alerts.value_objects import AlertId


async def get_owned_alert_or_raise(
    alert_repository: AlertRepository, alert_id: AlertId, requesting_user_id: str
) -> Alert:
    alert = await alert_repository.get_by_id(alert_id)
    if alert is None:
        raise AlertNotFoundError(f"No alert with id {alert_id}")
    if alert.user_id != requesting_user_id:
        raise AlertOwnershipError(f"User {requesting_user_id} does not own alert {alert_id}")
    return alert
