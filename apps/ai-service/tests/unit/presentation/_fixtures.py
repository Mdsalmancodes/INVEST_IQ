"""Shared test fixtures for AI/ML presentation-layer router tests —
builds a real FastAPI TestClient with all real routers wired, but with
the DI-injected repositories overridden to in-memory fakes so no real
HTTP call to core-api or real filesystem I/O occurs. Model wrappers
(LSTM/ARIMA/Prophet/RandomForest/XGBoost/FinBERT) run for REAL (not
mocked) — only the repository boundary is faked, matching how the
application-layer use case tests already isolate network/filesystem
while keeping real model training/inference.

Deliberately duplicates (rather than imports across test-package
boundaries via sys.path manipulation) the small FakeMarketDataRepository/
FakePredictionRunRepository/FakeModelRegistryRepository/synthetic_bars
helpers already defined in tests/unit/application/ml/_fixtures.py and
test_model_status_use_case.py — keeping each test package
self-contained and import-hack-free.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
from fastapi.testclient import TestClient

from src.config import get_settings
from src.domain.ml.entities import ModelVersion, PredictionRun
from src.domain.ml.repositories import OhlcvBar
from src.domain.ml.value_objects import ModelFamily, ModelVersionId, PredictionRunId
from src.main import app
from src.presentation.dependencies.ml_use_cases import (
    get_delete_model_use_case,
    get_forecast_use_case,
    get_model_status_use_case,
    get_portfolio_recommendation_use_case,
    get_predict_use_case,
    get_prediction_history_use_case,
    get_retrain_model_use_case,
    get_sentiment_analysis_use_case,
    get_train_model_use_case,
)

__all__ = [
    "FakeMarketDataRepository",
    "FakeModelRegistryRepository",
    "FakePredictionRunRepository",
    "app",
    "build_test_client",
    "override_all_ml_dependencies",
    "synthetic_bars",
]


def build_test_client() -> TestClient:
    """Every router test needs a TestClient that automatically carries the
    X-Internal-Service-Token header InternalServiceAuthMiddleware requires
    on every /api/v1/ml/* request (Phase 8) — centralizing that here means
    no individual test file needs to know the header's exact name or read
    the correct secret out of settings itself."""
    return TestClient(
        app, headers={"X-Internal-Service-Token": get_settings().internal_service_token}
    )


def synthetic_bars(n: int = 100, seed: int = 41, trend: float = 0.05) -> tuple[OhlcvBar, ...]:
    """Real, ascending-date synthetic OHLCV bars — ascending dates matter
    since Prophet's internal optimizer rejects a constant `ds` column."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=trend, scale=1.0, size=n)
    closes = 100 + np.cumsum(steps)
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    return tuple(
        OhlcvBar(
            bar_time=bar_date,
            open=float(c) - 0.5,
            high=float(c) + 1.0,
            low=float(c) - 1.0,
            close=float(c),
            adjusted_close=float(c),
            volume=500_000,
        )
        for bar_date, c in zip(dates, closes, strict=True)
    )


class FakeMarketDataRepository:
    def __init__(self, bars_by_symbol: dict[str, tuple[OhlcvBar, ...]] | None = None) -> None:
        self._bars_by_symbol = bars_by_symbol or {}
        self._default_bars: tuple[OhlcvBar, ...] = ()

    @classmethod
    def with_default_bars(cls, bars: tuple[OhlcvBar, ...]) -> FakeMarketDataRepository:
        instance = cls()
        instance._default_bars = bars
        return instance

    async def get_ohlcv_bars(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> tuple[OhlcvBar, ...]:
        return self._bars_by_symbol.get(symbol.upper(), self._default_bars)


class FakePredictionRunRepository:
    def __init__(self) -> None:
        self.saved: list[PredictionRun] = []

    async def save(self, prediction_run: PredictionRun) -> None:
        self.saved.append(prediction_run)

    async def get_by_id(self, prediction_run_id: PredictionRunId) -> PredictionRun | None:
        return next((r for r in self.saved if r.id == prediction_run_id), None)

    async def list_for_symbol(self, symbol: str, limit: int = 20) -> tuple[PredictionRun, ...]:
        matching = tuple(r for r in self.saved if r.symbol == symbol.upper())
        return tuple(reversed(matching))[:limit]


class FakeModelRegistryRepository:
    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []

    async def save(self, model_version: ModelVersion) -> None:
        for index, existing in enumerate(self._versions):
            if existing.id == model_version.id:
                self._versions[index] = model_version
                return
        self._versions.append(model_version)

    async def get_by_id(self, model_version_id: ModelVersionId) -> ModelVersion | None:
        return next((v for v in self._versions if v.id == model_version_id), None)

    async def get_active_for_family(self, family: ModelFamily) -> ModelVersion | None:
        active = [v for v in self._versions if v.family == family and v.status == "active"]
        return max(active, key=lambda v: v.trained_at) if active else None

    async def list_for_family(self, family: ModelFamily) -> tuple[ModelVersion, ...]:
        return tuple(v for v in self._versions if v.family == family)

    async def delete(self, model_version_id: ModelVersionId) -> bool:
        for index, existing in enumerate(self._versions):
            if existing.id == model_version_id:
                del self._versions[index]
                return True
        return False


def override_all_ml_dependencies(
    market_data_repository: FakeMarketDataRepository,
    prediction_run_repository: FakePredictionRunRepository | None = None,
    model_registry_repository: FakeModelRegistryRepository | None = None,
) -> None:
    """Overrides every ml-related FastAPI dependency with fakes wired to
    the given repositories, using FastAPI's real dependency_overrides
    mechanism (standard FastAPI testing pattern) — imported lazily inside
    the function body since these application-layer imports are only
    needed here, keeping the module's top-level import list to domain/
    presentation-layer names only."""
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

    prediction_run_repository = prediction_run_repository or FakePredictionRunRepository()
    model_registry_repository = model_registry_repository or FakeModelRegistryRepository()

    app.dependency_overrides[get_predict_use_case] = lambda: PredictUseCase(
        market_data_repository, prediction_run_repository, DecisionEngine()
    )
    app.dependency_overrides[get_forecast_use_case] = lambda: ForecastUseCase(
        market_data_repository
    )
    app.dependency_overrides[get_sentiment_analysis_use_case] = SentimentAnalysisUseCase
    app.dependency_overrides[get_portfolio_recommendation_use_case] = (
        lambda: PortfolioRecommendationUseCase(market_data_repository, DecisionEngine())
    )
    app.dependency_overrides[get_prediction_history_use_case] = (
        lambda: PredictionHistoryUseCase(prediction_run_repository)
    )
    app.dependency_overrides[get_delete_model_use_case] = lambda: DeleteModelUseCase(
        model_registry_repository
    )
    app.dependency_overrides[get_model_status_use_case] = lambda: ModelStatusUseCase(
        model_registry_repository
    )
    app.dependency_overrides[get_train_model_use_case] = lambda: TrainModelUseCase(
        market_data_repository, model_registry_repository, "./data/test-models"
    )
    app.dependency_overrides[get_retrain_model_use_case] = lambda: RetrainModelUseCase(
        market_data_repository, model_registry_repository, "./data/test-models"
    )
