"""Shared ownership-enforcement helper for portfolio use cases.

Document 3 §7.5's resource-level ownership rule, applied consistently
across every use case that operates on a specific portfolio_id — avoids
duplicating the same get-then-check pattern 7+ times.
"""

from __future__ import annotations

from src.domain.portfolio.entities import Portfolio
from src.domain.portfolio.exceptions import PortfolioNotFoundError, PortfolioOwnershipError
from src.domain.portfolio.repositories import PortfolioRepository
from src.domain.portfolio.value_objects import PortfolioId


async def get_owned_portfolio_or_raise(
    portfolio_repository: PortfolioRepository, portfolio_id: PortfolioId, requesting_user_id: str
) -> Portfolio:
    portfolio = await portfolio_repository.get_by_id(portfolio_id)
    if portfolio is None:
        raise PortfolioNotFoundError(f"No portfolio with id {portfolio_id}")
    if portfolio.user_id != requesting_user_id:
        raise PortfolioOwnershipError(
            f"User {requesting_user_id} does not own portfolio {portfolio_id}"
        )
    return portfolio
