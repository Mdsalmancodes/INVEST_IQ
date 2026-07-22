"""GetPortfolioSummaryUseCase — the read path backing the Portfolio
Dashboard's headline numbers, delegates all calculation logic to
PortfolioCalculationService (kept separate per Document 2 §4.1's
single-responsibility split between use cases and domain calculation
services)."""

from __future__ import annotations

from src.application.portfolio.calculation_service import (
    PortfolioCalculationService,
    PortfolioSummary,
)
from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.portfolio.repositories import PortfolioRepository
from src.domain.portfolio.value_objects import PortfolioId


class GetPortfolioSummaryUseCase:
    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        calculation_service: PortfolioCalculationService,
    ) -> None:
        self._portfolio_repository = portfolio_repository
        self._calculation_service = calculation_service

    async def execute(self, portfolio_id: PortfolioId, requesting_user_id: str) -> PortfolioSummary:
        portfolio = await get_owned_portfolio_or_raise(
            self._portfolio_repository, portfolio_id, requesting_user_id
        )
        return await self._calculation_service.compute_summary(portfolio)
