"""Dependency-injection wiring for AI/ML use cases — mirrors core-api's
presentation/dependencies/*_use_cases.py pattern exactly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from src.application.ml.decision_engine import DecisionEngine
from src.application.ml.delete_model_use_case import DeleteModelUseCase
from src.application.ml.forecast_use_case import ForecastUseCase
from src.application.ml.model_status_use_case import ModelStatusUseCase
from src.application.ml.portfolio_recommendation_use_case import (
    PortfolioRecommendationUseCase,
)
from src.application.ml.predict_use_case import PredictUseCase
from src.application.ml.prediction_history_use_case import PredictionHistoryUseCase
from src.application.ml.sentiment_analysis_use_case import SentimentAnalysisUseCase
from src.application.ml.train_model_use_case import RetrainModelUseCase, TrainModelUseCase
from src.config import Settings, get_settings
from src.domain.ml.repositories import MarketDataRepository, ModelRegistryRepository
from src.infrastructure.http.market_data_repository import HttpMarketDataRepository
from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)
from src.infrastructure.persistence.prediction_run_repository import (
    FileSystemPredictionRunRepository,
)


def get_market_data_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MarketDataRepository:
    return HttpMarketDataRepository(base_url=settings.core_api_base_url)


def get_model_registry_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelRegistryRepository:
    return FileSystemModelRegistryRepository(settings.ml_artifact_storage_path)


def get_prediction_run_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileSystemPredictionRunRepository:
    return FileSystemPredictionRunRepository(settings.ml_prediction_run_storage_path)


def get_predict_use_case(
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
    prediction_run_repository: Annotated[
        FileSystemPredictionRunRepository, Depends(get_prediction_run_repository)
    ],
) -> PredictUseCase:
    return PredictUseCase(market_data_repository, prediction_run_repository, DecisionEngine())


def get_forecast_use_case(
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
) -> ForecastUseCase:
    return ForecastUseCase(market_data_repository)


def get_sentiment_analysis_use_case() -> SentimentAnalysisUseCase:
    return SentimentAnalysisUseCase()


def get_portfolio_recommendation_use_case(
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
) -> PortfolioRecommendationUseCase:
    return PortfolioRecommendationUseCase(market_data_repository, DecisionEngine())


def get_prediction_history_use_case(
    prediction_run_repository: Annotated[
        FileSystemPredictionRunRepository, Depends(get_prediction_run_repository)
    ],
) -> PredictionHistoryUseCase:
    return PredictionHistoryUseCase(prediction_run_repository)


def get_model_status_use_case(
    model_registry_repository: Annotated[
        ModelRegistryRepository, Depends(get_model_registry_repository)
    ],
) -> ModelStatusUseCase:
    return ModelStatusUseCase(model_registry_repository)


def get_delete_model_use_case(
    model_registry_repository: Annotated[
        ModelRegistryRepository, Depends(get_model_registry_repository)
    ],
) -> DeleteModelUseCase:
    return DeleteModelUseCase(model_registry_repository)


def get_train_model_use_case(
    settings: Annotated[Settings, Depends(get_settings)],
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
    model_registry_repository: Annotated[
        ModelRegistryRepository, Depends(get_model_registry_repository)
    ],
) -> TrainModelUseCase:
    return TrainModelUseCase(
        market_data_repository, model_registry_repository, settings.ml_artifact_storage_path
    )


def get_retrain_model_use_case(
    settings: Annotated[Settings, Depends(get_settings)],
    market_data_repository: Annotated[
        MarketDataRepository, Depends(get_market_data_repository)
    ],
    model_registry_repository: Annotated[
        ModelRegistryRepository, Depends(get_model_registry_repository)
    ],
) -> RetrainModelUseCase:
    return RetrainModelUseCase(
        market_data_repository, model_registry_repository, settings.ml_artifact_storage_path
    )
