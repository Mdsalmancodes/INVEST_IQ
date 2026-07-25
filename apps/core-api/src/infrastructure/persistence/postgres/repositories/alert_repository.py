"""SqlAlchemyAlertRepository — implements
src.domain.alerts.repositories.AlertRepository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import AlertListFilter, AlertPageResult
from src.domain.alerts.value_objects import AlertId, InstrumentId
from src.infrastructure.persistence.postgres.alert_models import AlertModel
from src.infrastructure.persistence.postgres.repositories.alert_mappers import (
    alert_to_domain,
    alert_to_model,
)

_SORT_COLUMNS = {
    "created_at": AlertModel.created_at,
    "threshold": AlertModel.threshold,
}


class SqlAlchemyAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, alert: Alert) -> None:
        existing = await self._session.get(AlertModel, alert.id.value)
        model = alert_to_model(alert, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, alert_id: AlertId) -> Alert | None:
        model = await self._session.get(AlertModel, alert_id.value)
        return alert_to_domain(model) if model is not None else None

    async def list_for_user(self, user_id: str, filters: AlertListFilter) -> AlertPageResult:
        base_stmt = select(AlertModel).where(AlertModel.user_id == user_id)
        if filters.is_active is not None:
            base_stmt = base_stmt.where(AlertModel.is_active.is_(filters.is_active))

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        sort_column = _SORT_COLUMNS[filters.sort_by]
        ordered_column = (
            sort_column.desc() if filters.sort_direction == "desc" else sort_column.asc()
        )

        page_stmt = (
            base_stmt.order_by(ordered_column)
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        items = tuple(alert_to_domain(model) for model in models)
        return AlertPageResult(
            items=items, total_count=total_count, page=filters.page, page_size=filters.page_size
        )

    async def list_active_for_instrument(self, instrument_id: InstrumentId) -> tuple[Alert, ...]:
        # Uses idx_alerts_active_instrument (partial index on
        # is_active = true) — the alert evaluation engine's primary read
        # path, matched exactly to how that index was built (migration
        # 0005_alerts_context.py).
        stmt = select(AlertModel).where(
            AlertModel.instrument_id == instrument_id.value, AlertModel.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return tuple(alert_to_domain(model) for model in models)

    async def delete(self, alert_id: AlertId) -> None:
        model = await self._session.get(AlertModel, alert_id.value)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def exists_duplicate(
        self,
        user_id: str,
        instrument_id: InstrumentId,
        condition_type: str,
        threshold: object,
        exclude_alert_id: AlertId | None = None,
    ) -> bool:
        # Mirrors uq_alerts_duplicate exactly: UNIQUE(user_id,
        # instrument_id, condition_type, threshold).
        stmt = select(func.count()).select_from(AlertModel).where(
            AlertModel.user_id == user_id,
            AlertModel.instrument_id == instrument_id.value,
            AlertModel.condition_type == condition_type,
            AlertModel.threshold == threshold,
        )
        if exclude_alert_id is not None:
            stmt = stmt.where(AlertModel.id != exclude_alert_id.value)
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0
