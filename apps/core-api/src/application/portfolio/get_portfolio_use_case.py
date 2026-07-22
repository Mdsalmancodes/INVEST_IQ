"""GetPortfolioUseCase, ListPortfoliosUseCase — read-side use cases."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.portfolio.entities import Portfolio
from src.domain.portfolio.repositories import (
    PortfolioListFilter,
    PortfolioPageResult,
    PortfolioRepository,
)
from src.domain.portfolio.value_objects import PortfolioId


class GetPortfolioUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(self, portfolio_id: PortfolioId, requesting_user_id: str) -> Portfolio:
        return await get_owned_portfolio_or_raise(
            self._portfolio_repository, portfolio_id, requesting_user_id
        )


@dataclass(frozen=True, slots=True)
class ListPortfoliosQuery:
    user_id: str
    is_paper: bool | None = None
    page: int = 1
    page_size: int = 20


class ListPortfoliosUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(self, query: ListPortfoliosQuery) -> PortfolioPageResult:
        filters = PortfolioListFilter(
            is_paper=query.is_paper, page=query.page, page_size=query.page_size
        )
        return await self._portfolio_repository.list_for_user(query.user_id, filters)
