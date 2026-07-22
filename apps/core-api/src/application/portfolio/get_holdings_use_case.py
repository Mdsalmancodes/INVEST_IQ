"""GetHoldingsUseCase — returns the current holdings for a portfolio,
without price-dependent calculations (that's GetPortfolioSummaryUseCase's
job) — this is the plain, fast, no-external-dependency read path."""

from __future__ import annotations

from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.portfolio.entities import Holding
from src.domain.portfolio.repositories import PortfolioRepository
from src.domain.portfolio.value_objects import PortfolioId


class GetHoldingsUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(
        self, portfolio_id: PortfolioId, requesting_user_id: str
    ) -> tuple[Holding, ...]:
        portfolio = await get_owned_portfolio_or_raise(
            self._portfolio_repository, portfolio_id, requesting_user_id
        )
        return tuple(h for h in portfolio.holdings.values() if not h.quantity.is_zero())
