"""GetAlertUseCase, ListAlertsUseCase — read-side use cases."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.alerts.ownership import get_owned_alert_or_raise
from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import (
    AlertListFilter,
    AlertPageResult,
    AlertRepository,
    AlertSortField,
    SortDirection,
)
from src.domain.alerts.value_objects import AlertId


class GetAlertUseCase:
    def __init__(self, alert_repository: AlertRepository) -> None:
        self._alert_repository = alert_repository

    async def execute(self, alert_id: AlertId, requesting_user_id: str) -> Alert:
        return await get_owned_alert_or_raise(self._alert_repository, alert_id, requesting_user_id)


@dataclass(frozen=True, slots=True)
class ListAlertsQuery:
    user_id: str
    is_active: bool | None = None
    sort_by: AlertSortField = "created_at"
    sort_direction: SortDirection = "desc"
    page: int = 1
    page_size: int = 20


class ListAlertsUseCase:
    def __init__(self, alert_repository: AlertRepository) -> None:
        self._alert_repository = alert_repository

    async def execute(self, query: ListAlertsQuery) -> AlertPageResult:
        filters = AlertListFilter(
            is_active=query.is_active,
            sort_by=query.sort_by,
            sort_direction=query.sort_direction,
            page=query.page,
            page_size=query.page_size,
        )
        return await self._alert_repository.list_for_user(query.user_id, filters)
