"""CreatePortfolioUseCase and DeletePortfolioUseCase — Document 3 §3.4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.portfolio.entities import Portfolio
from src.domain.portfolio.repositories import PortfolioRepository
from src.domain.portfolio.value_objects import PortfolioId


@dataclass(frozen=True, slots=True)
class CreatePortfolioCommand:
    user_id: str
    name: str
    base_currency: str = "USD"
    is_paper: bool = True


class CreatePortfolioUseCase:
    def __init__(self, portfolio_repository: PortfolioRepository) -> None:
        self._portfolio_repository = portfolio_repository

    async def execute(self, command: CreatePortfolioCommand) -> Portfolio:
        now = datetime.now(UTC)
        portfolio = Portfolio(
            id=PortfolioId.new(),
            user_id=command.user_id,
            name=command.name,
            base_currency=command.base_currency,
            is_paper=command.is_paper,
            created_at=now,
            updated_at=now,
        )
        await self._portfolio_repository.save(portfolio)
        return portfolio
