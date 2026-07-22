"""SqlAlchemyLoginHistoryRepository — implements
src.domain.auth.repositories.LoginHistoryRepository (ADR-0002)."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.entities import LoginHistoryEntry
from src.domain.auth.value_objects import UserId
from src.infrastructure.persistence.postgres.models import LoginHistoryModel
from src.infrastructure.persistence.postgres.repositories.mappers import (
    login_history_to_domain,
    login_history_to_model,
)


class SqlAlchemyLoginHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: LoginHistoryEntry) -> None:
        self._session.add(login_history_to_model(entry))
        await self._session.flush()

    async def list_for_user(self, user_id: UserId, limit: int = 20) -> list[LoginHistoryEntry]:
        stmt = (
            select(LoginHistoryModel)
            .where(LoginHistoryModel.user_id == user_id.value)
            .order_by(desc(LoginHistoryModel.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [login_history_to_domain(model) for model in result.scalars().all()]
