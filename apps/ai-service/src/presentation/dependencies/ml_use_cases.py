"""
Dependency-injection wiring for INVEST IQ AI/ML use cases.

Architecture
============

API
  ↓
Presentation Dependency Injection
  ↓
Application Use Case
  ↓
Infrastructure
  ↓
real market data / trained model artifacts
  ↓
DecisionEngine
  ↓
prediction / recommendation result


IMPORTANT
=========

DecisionEngine is inference-only.

DecisionEngine must NOT be responsible for loading trained model
artifacts.

ModelLoader is responsible for:

    - resolving active model versions
    - locating trained artifacts
    - loading trained model instances
    - returning real ModelVersion IDs

PredictUseCase is the canonical single-symbol ML inference pipeline.

PortfolioRecommendationUseCase deliberately reuses PredictUseCase so
that portfolio recommendations and single-symbol recommendations use
exactly the same trained-model loading and inference architecture.

No synthetic/fake market data is used in this application path.

Filesystem repositories are used for:

    - model registry
    - prediction history
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends

from src.config import Settings, get_settings


# ============================================================================
# APPLICATION
# ============================================================================

from src.application.ml.decision_engine import (
    DecisionEngine,
)

from src.application.ml.delete_model_use_case import (
    DeleteModelUseCase,
)

from src.application.ml.forecast_use_case import (
    ForecastUseCase,
)

from src.application.ml.model_status_use_case import (
    ModelStatusUseCase,
)

from src.application.ml.portfolio_recommendation_use_case import (
    PortfolioRecommendationUseCase,
)

from src.application.ml.predict_use_case import (
    PredictUseCase,
)

from src.application.ml.prediction_history_use_case import (
    PredictionHistoryUseCase,
)

from src.application.ml.sentiment_analysis_use_case import (
    SentimentAnalysisUseCase,
)

from src.application.ml.train_model_use_case import (
    RetrainModelUseCase,
    TrainModelUseCase,
)


# ============================================================================
# DOMAIN
# ============================================================================

from src.domain.ml.repositories import (
    MarketDataRepository as MarketDataRepositoryPort,
    ModelRegistryRepository,
)


# ============================================================================
# INFRASTRUCTURE
# ============================================================================

from src.infrastructure.http.market_data_repository import (
    HttpMarketDataRepository,
)

from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)

from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.persistence.prediction_run_repository import (
    FileSystemPredictionRunRepository,
)


# ============================================================================
# SHARED HTTP CONFIGURATION
# ============================================================================

HTTP_CONNECT_TIMEOUT = 10.0
HTTP_READ_TIMEOUT = 300.0
HTTP_WRITE_TIMEOUT = 30.0
HTTP_POOL_TIMEOUT = 10.0


def _create_http_client() -> httpx.AsyncClient:
    """
    Create the HTTP client used by the market-data repository.

    The client is explicitly closed by get_market_data_repository()
    after the dependency scope finishes.
    """

    timeout = httpx.Timeout(
        connect=HTTP_CONNECT_TIMEOUT,
        read=HTTP_READ_TIMEOUT,
        write=HTTP_WRITE_TIMEOUT,
        pool=HTTP_POOL_TIMEOUT,
    )

    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    )


# ============================================================================
# MARKET DATA REPOSITORY
# ============================================================================


async def get_market_data_repository(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> AsyncIterator[MarketDataRepositoryPort]:
    """
    Provide the real HTTP market-data repository.

    Runtime flow:

        AI service
            ↓
        Settings.core_api_base_url
            ↓
        HttpMarketDataRepository
            ↓
        core-api
            ↓
        real OHLCV market data

    No synthetic market data is generated here.
    """

    client = _create_http_client()

    repository = HttpMarketDataRepository(
        base_url=settings.core_api_base_url,
        client=client,
    )

    try:
        yield repository

    finally:
        await client.aclose()


# ============================================================================
# MODEL REGISTRY REPOSITORY
# ============================================================================


def get_model_registry_repository(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> ModelRegistryRepository:
    """
    Provide the filesystem-backed model registry.

    The registry is the source of truth for:

        - model families
        - model versions
        - active versions
        - artifact locations
    """

    return FileSystemModelRegistryRepository(
        settings.ml_model_registry_storage_path,
    )


# ============================================================================
# PREDICTION RUN REPOSITORY
# ============================================================================


def get_prediction_run_repository(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> FileSystemPredictionRunRepository:
    """
    Provide filesystem-backed prediction-run persistence.
    """

    return FileSystemPredictionRunRepository(
        settings.ml_prediction_run_storage_path,
    )


# ============================================================================
# MODEL LOADER
# ============================================================================


def get_model_loader(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
    model_registry_repository: Annotated[
        ModelRegistryRepository,
        Depends(get_model_registry_repository),
    ],
) -> ModelLoader:
    """
    Provide the trained-model loader.

    ModelLoader is responsible for:

        model registry
              ↓
        active ModelVersion
              ↓
        artifact location
              ↓
        trained model instance

    Expected model families include:

        - LSTM
        - ARIMA
        - Prophet
        - Random Forest
        - XGBoost
        - FinBERT where supported by the registry

    IMPORTANT:

    This dependency does NOT train models.

    It only loads already-trained model artifacts.
    """

    return ModelLoader(
        model_registry_repository=model_registry_repository,
        artifact_root=settings.ml_artifact_storage_path,
    )


# ============================================================================
# DECISION ENGINE
# ============================================================================


def get_decision_engine() -> DecisionEngine:
    """
    Provide a clean inference-only DecisionEngine.

    IMPORTANT:

    Do NOT instantiate model classes here.

    Never do:

        LstmModel()
        ArimaModel()
        ProphetModel()
        RandomForestModel()
        XgboostModel()

    PredictUseCase loads the actual trained models through ModelLoader
    and injects them into DecisionEngine before inference.
    """

    return DecisionEngine()


# ============================================================================
# PREDICT USE CASE
# ============================================================================


def get_predict_use_case(
    market_data_repository: Annotated[
        MarketDataRepositoryPort,
        Depends(get_market_data_repository),
    ],
    prediction_run_repository: Annotated[
        FileSystemPredictionRunRepository,
        Depends(get_prediction_run_repository),
    ],
    model_loader: Annotated[
        ModelLoader,
        Depends(get_model_loader),
    ],
) -> PredictUseCase:
    """
    Provide the canonical single-symbol prediction use case.

    Runtime flow:

        symbol
          ↓
        real market data
          ↓
        OHLCV normalization
          ↓
        ModelLoader
          ↓
        trained model artifacts
          ↓
        real ModelVersion IDs
          ↓
        DecisionEngine
          ↓
        ensemble recommendation
          ↓
        prediction persistence
          ↓
        result

    This is the primary ML inference pipeline.
    """

    return PredictUseCase(
        market_data_repository=market_data_repository,
        prediction_run_repository=prediction_run_repository,
        decision_engine=get_decision_engine(),
        model_loader=model_loader,
    )


# ============================================================================
# FORECAST USE CASE
# ============================================================================


def get_forecast_use_case(
    market_data_repository: Annotated[
        MarketDataRepositoryPort,
        Depends(get_market_data_repository),
    ],
) -> ForecastUseCase:
    """
    Provide the dedicated forecast comparison use case.

    ForecastUseCase retrieves real historical market data from core-api
    and performs its dedicated LSTM / ARIMA / Prophet forecast workflow.
    """

    return ForecastUseCase(
        market_data_repository=market_data_repository,
    )


# ============================================================================
# SENTIMENT ANALYSIS USE CASE
# ============================================================================


def get_sentiment_analysis_use_case() -> SentimentAnalysisUseCase:
    """
    Provide the dedicated sentiment-analysis use case.

    Flow:

        news text
            ↓
        FinBERT
            ↓
        per-item sentiment
            ↓
        aggregate sentiment
    """

    return SentimentAnalysisUseCase()


# ============================================================================
# PORTFOLIO RECOMMENDATION USE CASE
# ============================================================================


def get_portfolio_recommendation_use_case(
    predict_use_case: Annotated[
        PredictUseCase,
        Depends(get_predict_use_case),
    ],
) -> PortfolioRecommendationUseCase:
    """
    Provide the portfolio-recommendation use case.

    IMPORTANT ARCHITECTURAL RULE
    =============================

    PortfolioRecommendationUseCase MUST reuse PredictUseCase.

    It must NOT create its own bare DecisionEngine.

    BROKEN ARCHITECTURE:

        PortfolioRecommendationUseCase
                ↓
        DecisionEngine()
                ↓
        no trained models
                ↓
        NO MODELS PRODUCED SIGNALS
                ↓
        ValueError:
        Recommendation requires at least one contributing model


    CORRECT ARCHITECTURE:

        PortfolioRecommendationUseCase
                ↓
        PredictUseCase
                ↓
        real market data
                ↓
        ModelLoader
                ↓
        active trained model artifacts
                ↓
        real ModelVersion IDs
                ↓
        DecisionEngine
                ↓
        BUY / SELL / HOLD


    Therefore both:

        /api/v1/ml/predict

    and:

        /api/v1/ml/portfolio-recommendation

    use the same trained-model inference pipeline.
    """

    return PortfolioRecommendationUseCase(
        predict_use_case=predict_use_case,
    )


# ============================================================================
# PREDICTION HISTORY USE CASE
# ============================================================================


def get_prediction_history_use_case(
    prediction_run_repository: Annotated[
        FileSystemPredictionRunRepository,
        Depends(get_prediction_run_repository),
    ],
) -> PredictionHistoryUseCase:
    """
    Provide prediction-history operations.
    """

    return PredictionHistoryUseCase(
        prediction_run_repository=prediction_run_repository,
    )


# ============================================================================
# MODEL STATUS USE CASE
# ============================================================================


def get_model_status_use_case(
    model_registry_repository: Annotated[
        ModelRegistryRepository,
        Depends(get_model_registry_repository),
    ],
) -> ModelStatusUseCase:
    """
    Provide model-status operations.

    The model registry remains the source of truth for:

        - model family
        - active version
        - version count
        - model status
        - artifact location
    """

    return ModelStatusUseCase(
        model_registry_repository=model_registry_repository,
    )


# ============================================================================
# DELETE MODEL USE CASE
# ============================================================================


def get_delete_model_use_case(
    model_registry_repository: Annotated[
        ModelRegistryRepository,
        Depends(get_model_registry_repository),
    ],
) -> DeleteModelUseCase:
    """
    Provide model-deletion operations.
    """

    return DeleteModelUseCase(
        model_registry_repository=model_registry_repository,
    )


# ============================================================================
# TRAIN MODEL USE CASE
# ============================================================================


def get_train_model_use_case(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
    market_data_repository: Annotated[
        MarketDataRepositoryPort,
        Depends(get_market_data_repository),
    ],
    model_registry_repository: Annotated[
        ModelRegistryRepository,
        Depends(get_model_registry_repository),
    ],
) -> TrainModelUseCase:
    """
    Provide the model-training use case.

    Training flow:

        real historical market data
              ↓
        feature preparation
              ↓
        model training
              ↓
        validation
              ↓
        artifact storage
              ↓
        ModelVersion registration
    """

    return TrainModelUseCase(
        market_data_repository=market_data_repository,
        model_registry_repository=model_registry_repository,
        artifact_storage_root=settings.ml_artifact_storage_path,
    )


# ============================================================================
# RETRAIN MODEL USE CASE
# ============================================================================


def get_retrain_model_use_case(
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
    market_data_repository: Annotated[
        MarketDataRepositoryPort,
        Depends(get_market_data_repository),
    ],
    model_registry_repository: Annotated[
        ModelRegistryRepository,
        Depends(get_model_registry_repository),
    ],
) -> RetrainModelUseCase:
    """
    Provide the model-retraining use case.

    Retraining flow:

        real historical market data
              ↓
        retrain model
              ↓
        validation
              ↓
        artifact storage
              ↓
        new ModelVersion
    """

    return RetrainModelUseCase(
        market_data_repository=market_data_repository,
        model_registry_repository=model_registry_repository,
        artifact_storage_root=settings.ml_artifact_storage_path,
    )