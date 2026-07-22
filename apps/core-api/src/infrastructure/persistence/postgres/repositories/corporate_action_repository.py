"""SqlAlchemyCorporateActionRepository — implements
src.domain.market_data.repositories.CorporateActionRepository."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.market_data.entities import CorporateAction
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId
from src.infrastructure.persistence.postgres.market_data_models import CorporateActionModel
from src.infrastructure.persistence.postgres.repositories.market_data_mappers import (
    corporate_action_to_domain,
    corporate_action_to_model,
)


class SqlAlchemyCorporateActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, action: CorporateAction) -> None:
        # Append-only per this repository's docstring convention (see
        # market_data_mappers.corporate_action_to_model) — always inserts.
        model = corporate_action_to_model(action)
        self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, action_id: CorporateActionId) -> CorporateAction | None:
        model = await self._session.get(CorporateActionModel, action_id.value)
        return corporate_action_to_domain(model) if model is not None else None

    async def list_for_instrument(self, instrument_id: InstrumentId) -> tuple[CorporateAction, ...]:
        stmt = (
            select(CorporateActionModel)
            .where(CorporateActionModel.instrument_id == instrument_id.value)
            .order_by(CorporateActionModel.ex_date.desc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return tuple(corporate_action_to_domain(model) for model in models)

    async def exists(self, instrument_id: InstrumentId, action_type: str, ex_date: date) -> bool:
        stmt = select(CorporateActionModel.id).where(
            CorporateActionModel.instrument_id == instrument_id.value,
            CorporateActionModel.action_type == action_type,
            CorporateActionModel.ex_date == ex_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
