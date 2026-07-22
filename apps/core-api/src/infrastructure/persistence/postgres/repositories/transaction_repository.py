"""SqlAlchemyTransactionRepository — implements
src.domain.portfolio.repositories.TransactionRepository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from src.domain.portfolio.entities import Transaction
from src.domain.portfolio.repositories import PageResult, TransactionFilter
from src.domain.portfolio.value_objects import PortfolioId, TransactionId
from src.infrastructure.persistence.postgres.portfolio_models import TransactionModel
from src.infrastructure.persistence.postgres.repositories.portfolio_mappers import (
    transaction_to_domain,
    transaction_to_model,
)


class SqlAlchemyTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, transaction: Transaction) -> None:
        # Append-only per Document 3 §3.4 — always an insert.
        model = transaction_to_model(transaction)
        self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, transaction_id: TransactionId) -> Transaction | None:
        model = await self._session.get(TransactionModel, transaction_id.value)
        return transaction_to_domain(model) if model is not None else None

    def _build_filtered_stmt(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> Select[tuple[TransactionModel]]:
        stmt = select(TransactionModel).where(TransactionModel.portfolio_id == portfolio_id.value)
        if filters.instrument_id is not None:
            stmt = stmt.where(TransactionModel.instrument_id == filters.instrument_id.value)
        if filters.types is not None:
            stmt = stmt.where(TransactionModel.type.in_([t.value for t in filters.types]))
        if filters.executed_after is not None:
            stmt = stmt.where(TransactionModel.executed_at >= filters.executed_after)
        if filters.executed_before is not None:
            stmt = stmt.where(TransactionModel.executed_at <= filters.executed_before)
        return stmt

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult:
        base_stmt = self._build_filtered_stmt(portfolio_id, filters)

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = (await self._session.execute(count_stmt)).scalar_one()

        page_stmt = (
            base_stmt.order_by(TransactionModel.executed_at.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self._session.execute(page_stmt)
        models = result.scalars().all()
        items = tuple(transaction_to_domain(model) for model in models)
        return PageResult(
            items=items, total_count=total_count, page=filters.page, page_size=filters.page_size
        )

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        stmt = (
            select(TransactionModel)
            .where(TransactionModel.portfolio_id == portfolio_id.value)
            .order_by(TransactionModel.executed_at.asc())
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return tuple(transaction_to_domain(model) for model in models)
