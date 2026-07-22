"""UpdatePortfolioUseCase, DeletePortfolioUseCase."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.portfolio.entities import Portfolio
from src.domain.portfolio.repositories import PortfolioRepository
from src.domain.portfolio.value_objects import PortfolioId


@dataclass(frozen=True, slots=True)
class UpdatePortfolioCommand:
    portfolio_id: PortfolioId
    requesting_user_id: str
    name: str | None = None
    base_currency: str | None = None


class UpdatePortfolioUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(self, command: UpdatePortfolioCommand) -> Portfolio:
        portfolio = await get_owned_portfolio_or_raise(
            self._portfolio_repository, command.portfolio_id, command.requesting_user_id
        )
        if command.name is not None:
            portfolio.name = command.name
        if command.base_currency is not None:
            portfolio.base_currency = command.base_currency
        portfolio.updated_at = datetime.now(UTC)
        await self._portfolio_repository.save(portfolio)
        return portfolio


class DeletePortfolioUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(self, portfolio_id: PortfolioId, requesting_user_id: str) -> None:
        await get_owned_portfolio_or_raise(
            self._portfolio_repository, portfolio_id, requesting_user_id
        )
        await self._portfolio_repository.delete(portfolio_id)
