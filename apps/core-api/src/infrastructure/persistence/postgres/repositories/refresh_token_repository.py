"""SqlAlchemyRefreshTokenRepository — implements
src.domain.auth.repositories.RefreshTokenRepository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.entities import RefreshToken
from src.domain.auth.value_objects import UserId
from src.infrastructure.persistence.postgres.models import RefreshTokenModel
from src.infrastructure.persistence.postgres.repositories.mappers import (
    refresh_token_to_domain,
    refresh_token_to_model,
)


class SqlAlchemyRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, token: RefreshToken) -> None:
        existing = await self._session.get(RefreshTokenModel, token.id.value)
        if existing is not None:
            existing.revoked_at = token.revoked_at
        else:
            self._session.add(refresh_token_to_model(token))
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshTokenModel).where(RefreshTokenModel.token_hash == token_hash)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return refresh_token_to_domain(model) if model is not None else None

    async def revoke_all_for_user(self, user_id: UserId, at: datetime) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id.value)
            .where(RefreshTokenModel.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        await self._session.execute(stmt)
        await self._session.flush()
