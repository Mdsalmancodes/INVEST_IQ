"""SqlAlchemyInstrumentRepository — implements
src.domain.market_data.repositories.InstrumentRepository."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.market_data.entities import Instrument
from src.domain.market_data.value_objects import InstrumentId
from src.infrastructure.persistence.postgres.portfolio_models import InstrumentModel
from src.infrastructure.persistence.postgres.repositories.market_data_mappers import (
    instrument_to_domain,
    instrument_to_model,
)


class SqlAlchemyInstrumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, instrument: Instrument) -> None:
        existing = await self._session.get(InstrumentModel, instrument.id.value)
        model = instrument_to_model(instrument, existing=existing)
        if existing is None:
            self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        model = await self._session.get(InstrumentModel, instrument_id.value)
        return instrument_to_domain(model) if model is not None else None

    async def get_by_symbol(self, symbol: str) -> Instrument | None:
        # Resolves via idx_instruments_symbol_global (Document 3 §8.1
        # revision) — case-sensitive exact match, matching how the global
        # partial unique index itself is defined (no LOWER()/citext on
        # this column, unlike users.email).
        stmt = select(InstrumentModel).where(
            InstrumentModel.symbol == symbol, InstrumentModel.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return instrument_to_domain(model) if model is not None else None

    async def search(self, query: str, limit: int = 20) -> tuple[Instrument, ...]:
        pattern = f"%{query}%"
        stmt = (
            select(InstrumentModel)
            .where(
                InstrumentModel.is_active.is_(True),
                or_(
                    InstrumentModel.symbol.ilike(pattern),
                    InstrumentModel.name.ilike(pattern),
                ),
            )
            .order_by(InstrumentModel.symbol)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return tuple(instrument_to_domain(model) for model in models)
