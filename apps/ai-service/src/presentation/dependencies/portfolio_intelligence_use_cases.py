"""Dependency-injection wiring for Phase 10 Portfolio Intelligence use
cases — mirrors ml_use_cases.py's exact pattern (reuses the SAME
get_market_data_repository provider, never a second/duplicate one).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceUseCase,
)
from src.domain.ml.repositories import MarketDataRepository
from src.presentation.dependencies.ml_use_cases import get_market_data_repository


def get_portfolio_intelligence_use_case(
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
) -> PortfolioIntelligenceUseCase:
    return PortfolioIntelligenceUseCase(market_data_repository)


def get_monte_carlo_use_case(
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
) -> MonteCarloUseCase:
    return MonteCarloUseCase(market_data_repository)
