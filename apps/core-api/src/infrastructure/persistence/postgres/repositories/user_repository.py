"""SqlAlchemyUserRepository — implements src.domain.auth.repositories.UserRepository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.auth.entities import User
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.persistence.postgres.models import UserModel
from src.infrastructure.persistence.postgres.repositories.mappers import (
    user_to_domain,
    user_to_model,
)


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, user: User) -> None:
        existing = await self._session.get(UserModel, user.id.value)
        model = user_to_model(user, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, user_id: UserId) -> User | None:
        model = await self._session.get(UserModel, user_id.value)
        return user_to_domain(model) if model is not None else None

    async def get_by_email(self, email: Email) -> User | None:
        stmt = select(UserModel).where(UserModel.email == str(email))
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return user_to_domain(model) if model is not None else None

    async def exists_with_email(self, email: Email) -> bool:
        stmt = select(UserModel.id).where(UserModel.email == str(email))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
