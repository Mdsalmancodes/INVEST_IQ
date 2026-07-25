"""Unit tests for TrainModelUseCase and RetrainModelUseCase. Trains REAL
models (small synthetic datasets, not mocked) and saves real artifacts
to a tmp_path directory.
"""

from __future__ import annotations

import pytest

from src.application.ml.train_model_use_case import (
    RetrainModelUseCase,
    TrainModelCommand,
    TrainModelUseCase,
)
from src.domain.ml.exceptions import InsufficientDataError
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars
from tests.unit.application.ml.test_model_status_use_case import FakeModelRegistryRepository


class TestTrainModelUseCase:
    async def test_raises_for_finbert(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        registry_repo = FakeModelRegistryRepository()
        use_case = TrainModelUseCase(market_data_repo, registry_repo, tmp_path)

        with pytest.raises(ValueError, match="pretrained model"):
            await use_case.execute(TrainModelCommand(family="finbert", symbol="AAPL"))

    async def test_raises_when_no_bars_available(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(())
        registry_repo = FakeModelRegistryRepository()
        use_case = TrainModelUseCase(market_data_repo, registry_repo, tmp_path)

        with pytest.raises(InsufficientDataError, match="No OHLCV history"):
            await use_case.execute(TrainModelCommand(family="lstm", symbol="AAPL"))

    async def test_trains_lstm_and_saves_artifact_and_version(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        registry_repo = FakeModelRegistryRepository()
        use_case = TrainModelUseCase(market_data_repo, registry_repo, tmp_path)

        result = await use_case.execute(TrainModelCommand(family="lstm", symbol="aapl"))

        assert result.model_version.family == "lstm"
        assert "rmse" in result.validation_metrics
        assert len(registry_repo._versions) == 1

    async def test_trains_random_forest_and_saves_artifact_and_version(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        registry_repo = FakeModelRegistryRepository()
        use_case = TrainModelUseCase(market_data_repo, registry_repo, tmp_path)

        result = await use_case.execute(TrainModelCommand(family="random_forest", symbol="AAPL"))

        assert result.model_version.family == "random_forest"
        assert "accuracy" in result.validation_metrics


class TestRetrainModelUseCase:
    async def test_retires_previous_active_version_before_training_new_one(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        registry_repo = FakeModelRegistryRepository()
        train_use_case = TrainModelUseCase(market_data_repo, registry_repo, tmp_path)
        await train_use_case.execute(TrainModelCommand(family="arima", symbol="AAPL"))

        retrain_use_case = RetrainModelUseCase(market_data_repo, registry_repo, tmp_path)
        await retrain_use_case.execute(TrainModelCommand(family="arima", symbol="AAPL"))

        all_versions = await registry_repo.list_for_family("arima")
        assert len(all_versions) == 2
        retired = [v for v in all_versions if v.status == "retired"]
        active = [v for v in all_versions if v.status == "active"]
        assert len(retired) == 1
        assert len(active) == 1

    async def test_succeeds_when_no_previous_version_exists(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        registry_repo = FakeModelRegistryRepository()
        use_case = RetrainModelUseCase(market_data_repo, registry_repo, tmp_path)

        result = await use_case.execute(TrainModelCommand(family="xgboost", symbol="AAPL"))

        assert result.model_version.status == "active"
