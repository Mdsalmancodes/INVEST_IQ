"""SqlAlchemyPortfolioRepository — implements
src.domain.portfolio.repositories.PortfolioRepository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.portfolio.entities import Portfolio
from src.domain.portfolio.repositories import PortfolioListFilter, PortfolioPageResult
from src.domain.portfolio.value_objects import PortfolioId
from src.infrastructure.persistence.postgres.portfolio_models import PortfolioModel
from src.infrastructure.persistence.postgres.repositories.portfolio_mappers import (
    holding_to_model,
    portfolio_to_domain,
    portfolio_to_model,
)


class SqlAlchemyPortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, portfolio: Portfolio) -> None:
        existing = await self._session.get(
            PortfolioModel, portfolio.id.value, options=[selectinload(PortfolioModel.holdings)]
        )
        model = portfolio_to_model(portfolio, existing=existing)
        if existing is None:
            self._session.add(model)

        existing_holding_models_by_instrument = (
            {str(h.instrument_id): h for h in existing.holdings} if existing is not None else {}
        )
        for holding in portfolio.holdings.values():
            existing_holding_model = existing_holding_models_by_instrument.get(
                str(holding.instrument_id)
            )
            holding_model = holding_to_model(holding, existing=existing_holding_model)
            if existing_holding_model is None:
                holding_model.portfolio_id = portfolio.id.value
                self._session.add(holding_model)

        await self._session.flush()

    async def get_by_id(self, portfolio_id: PortfolioId) -> Portfolio | None:
        stmt = (
            select(PortfolioModel)
            .where(PortfolioModel.id == portfolio_id.value)
            .options(selectinload(PortfolioModel.holdings))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return portfolio_to_domain(model) if model is not None else None

    async def list_for_user(
        self, user_id: str, filters: PortfolioListFilter
    ) -> PortfolioPageResult:
        base_stmt = select(PortfolioModel).where(PortfolioModel.user_id == user_id)
        if filters.is_paper is not None:
            base_stmt = base_stmt.where(PortfolioModel.is_paper == filters.is_paper)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        page_stmt = (
            base_stmt.options(selectinload(PortfolioModel.holdings))
            .order_by(PortfolioModel.created_at.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        items = tuple(portfolio_to_domain(model) for model in models)
        return PortfolioPageResult(
            items=items, total_count=total_count, page=filters.page, page_size=filters.page_size
        )

    async def delete(self, portfolio_id: PortfolioId) -> None:
        model = await self._session.get(PortfolioModel, portfolio_id.value)
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def exists_with_name_for_user(self, user_id: str, name: str) -> bool:
        stmt = select(PortfolioModel.id).where(
            PortfolioModel.user_id == user_id, PortfolioModel.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
