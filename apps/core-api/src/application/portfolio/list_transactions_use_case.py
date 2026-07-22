"""ListTransactionsUseCase — paginated/filtered transaction history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.portfolio.entities import TransactionType
from src.domain.portfolio.repositories import (
    PageResult,
    PortfolioRepository,
    TransactionFilter,
    TransactionRepository,
)
from src.domain.portfolio.value_objects import InstrumentId, PortfolioId


@dataclass(frozen=True, slots=True)
class ListTransactionsQuery:
    portfolio_id: PortfolioId
    requesting_user_id: str
    instrument_id: InstrumentId | None = None
    types: tuple[TransactionType, ...] | None = None
    executed_after: datetime | None = None
    executed_before: datetime | None = None
    page: int = 1
    page_size: int = 20


class ListTransactionsUseCase:
    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        transaction_repository: TransactionRepository,
    ) -> None:
        self._portfolio_repository = portfolio_repository
        self._transaction_repository = transaction_repository

    async def execute(self, query: ListTransactionsQuery) -> PageResult:
        await get_owned_portfolio_or_raise(
            self._portfolio_repository, query.portfolio_id, query.requesting_user_id
        )
        filters = TransactionFilter(
            instrument_id=query.instrument_id,
            types=query.types,
            executed_after=query.executed_after,
            executed_before=query.executed_before,
            page=query.page,
            page_size=query.page_size,
        )
        return await self._transaction_repository.list_for_portfolio(query.portfolio_id, filters)
