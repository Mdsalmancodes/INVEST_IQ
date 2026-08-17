"""
Dependency-injection wiring for Phase 10 Portfolio Intelligence.

The dependency graph is:

    MarketDataRepository
            +
       ModelLoader
            ↓
    AiPortfolioEngineService
            ↓
    PortfolioIntelligenceUseCase

The SAME market-data repository provider used by ml_use_cases.py
is reused here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioEngineService,
)
from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceUseCase,
)
from src.domain.ml.repositories import MarketDataRepository
from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)
from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)
from src.presentation.dependencies.ml_use_cases import (
    get_market_data_repository,
)


# ============================================================================
# MODEL LOADER
# ============================================================================


@lru_cache(maxsize=1)
def get_model_loader() -> ModelLoader:
    """
    Create and cache the application's ModelLoader.

    The loader uses:

        /app/data/model_registry
            ↓
        model registry metadata

        /app/data/models
            ↓
        trained model artifacts
    """

    repository = FileSystemModelRegistryRepository(
        "/app/data/model_registry"
    )

    return ModelLoader(
        repository,
        "/app/data/models",
    )


# ============================================================================
# AI PORTFOLIO ENGINE SERVICE
# ============================================================================


def get_ai_portfolio_engine_service(
    model_loader: Annotated[
        ModelLoader,
        Depends(get_model_loader),
    ],
) -> AiPortfolioEngineService:
    """
    Construct the Phase 10 AI Portfolio Engine using the
    existing trained-model loader.
    """

    return AiPortfolioEngineService(
        model_loader=model_loader,
    )


# ============================================================================
# PORTFOLIO INTELLIGENCE USE CASE
# ============================================================================


def get_portfolio_intelligence_use_case(
    market_data_repository: Annotated[
        MarketDataRepository,
        Depends(get_market_data_repository),
    ],
    ai_portfolio_engine_service: Annotated[
        AiPortfolioEngineService,
        Depends(get_ai_portfolio_engine_service),
    ],
) -> PortfolioIntelligenceUseCase:
    """
    Construct the complete Phase 10 portfolio intelligence use case.
    """

    return PortfolioIntelligenceUseCase(
        market_data_repository=market_data_repository,
        ai_portfolio_engine_service=ai_portfolio_engine_service,
    )


# ============================================================================
# MONTE CARLO USE CASE
# ============================================================================


def get_monte_carlo_use_case(
    market_data_repository: Annotated[
        MarketDataRepository,
        Depends(get_market_data_repository),
    ],
) -> MonteCarloUseCase:
    """
    Construct the dedicated Monte Carlo use case.
    """

    return MonteCarloUseCase(
        market_data_repository=market_data_repository,
    )