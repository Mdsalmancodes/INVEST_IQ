"""SqlAlchemyNotificationRepository — implements
src.domain.notifications.repositories.NotificationRepository."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.notifications.entities import Notification
from src.domain.notifications.repositories import NotificationListFilter, NotificationPageResult
from src.domain.notifications.value_objects import NotificationId
from src.infrastructure.persistence.postgres.alert_models import NotificationModel
from src.infrastructure.persistence.postgres.repositories.notification_mappers import (
    notification_to_domain,
    notification_to_model,
)


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, notification: Notification) -> None:
        existing = await self._session.get(NotificationModel, notification.id.value)
        model = notification_to_model(notification, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        model = await self._session.get(NotificationModel, notification_id.value)
        return notification_to_domain(model) if model is not None else None

    async def list_for_user(
        self, user_id: str, filters: NotificationListFilter
    ) -> NotificationPageResult:
        base_stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)

        unread_count_stmt = select(func.count()).select_from(
            base_stmt.where(NotificationModel.read_at.is_(None)).subquery()
        )
        unread_count = (await self._session.execute(unread_count_stmt)).scalar_one()

        filtered_stmt = (
            base_stmt.where(NotificationModel.read_at.is_(None))
            if filters.unread_only
            else base_stmt
        )
        count_stmt = select(func.count()).select_from(filtered_stmt.subquery())
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        page_stmt = (
            filtered_stmt.order_by(NotificationModel.created_at.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        items = tuple(notification_to_domain(model) for model in models)
        return NotificationPageResult(
            items=items,
            total_count=total_count,
            unread_count=unread_count,
            page=filters.page,
            page_size=filters.page_size,
        )

    async def mark_all_as_read_for_user(self, user_id: str) -> int:
        # Bulk UPDATE, not a load-every-row-then-save loop — matches the
        # Protocol's documented intent of avoiding N+1 entity hydration
        # for what is fundamentally a single-statement operation.
        stmt = (
            update(NotificationModel)
            .where(NotificationModel.user_id == user_id, NotificationModel.read_at.is_(None))
            .values(read_at=func.now())
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        # AsyncSession.execute() is typed to return the generic Result[Any]
        # (no rowcount attribute in that stub), but a real UPDATE statement
        # actually returns a CursorResult at runtime, which does have
        # rowcount — a documented SQLAlchemy 2 async typing gap, not a bug
        # in this code (see ohlcv_bar_repository.py for the same pattern).
        # Scoped ignore, not a blanket suppression.
        return int(result.rowcount)  # type: ignore[attr-defined]
