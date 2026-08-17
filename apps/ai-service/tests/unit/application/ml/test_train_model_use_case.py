"""Unit tests for TrainModelUseCase and RetrainModelUseCase."""

from __future__ import annotations

import pytest

from src.application.ml.train_model_use_case import (
    RetrainModelUseCase,
    TrainModelCommand,
    TrainModelUseCase,
)

from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    synthetic_bars,
)

from tests.unit.application.ml.test_model_status_use_case import (
    FakeModelRegistryRepository,
)


class TestTrainModelUseCase:

    async def test_raises_for_finbert(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(100)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        with pytest.raises(
            ValueError,
            match="pretrained model",
        ):
            await use_case.execute(
                TrainModelCommand(
                    family="finbert",
                    symbol="AAPL",
                )
            )

    async def test_trains_lstm_and_saves_artifact_and_version(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        # LSTM production requirement is 120 observations.
        # The old test supplied only 100.
        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(150)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        result = await use_case.execute(
            TrainModelCommand(
                family="lstm",
                symbol="aapl",
            )
        )

        assert result.symbol == "AAPL"
        assert result.family == "lstm"
        assert result.status == "active"

        assert result.version_tag

        assert result.artifact_location

        assert (
            result.validation_metrics
        )

        saved_version = (
            await registry_repo.get_active_for_family_and_symbol(
                "lstm",
                "AAPL",
            )
        )

        assert saved_version is not None

        assert saved_version.symbol == "AAPL"
        assert saved_version.family == "lstm"
        assert saved_version.status == "active"

        assert saved_version.artifact_location

    async def test_trains_arima(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(100)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        result = await use_case.execute(
            TrainModelCommand(
                family="arima",
                symbol="AAPL",
            )
        )

        assert result.symbol == "AAPL"
        assert result.family == "arima"
        assert result.status == "active"

        saved_version = (
            await registry_repo.get_active_for_family_and_symbol(
                "arima",
                "AAPL",
            )
        )

        assert saved_version is not None
        assert saved_version.symbol == "AAPL"

    async def test_trains_prophet(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(150)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        result = await use_case.execute(
            TrainModelCommand(
                family="prophet",
                symbol="AAPL",
            )
        )

        assert result.symbol == "AAPL"
        assert result.family == "prophet"
        assert result.status == "active"

        saved_version = (
            await registry_repo.get_active_for_family_and_symbol(
                "prophet",
                "AAPL",
            )
        )

        assert saved_version is not None
        assert saved_version.symbol == "AAPL"

    async def test_rejects_empty_symbol(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(100)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        with pytest.raises(
            ValueError,
            match="symbol",
        ):
            await use_case.execute(
                TrainModelCommand(
                    family="arima",
                    symbol="",
                )
            )


class TestRetrainModelUseCase:

    async def test_retires_previous_active_version_before_training_new_one(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(100)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        train_use_case = TrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        first_result = await train_use_case.execute(
            TrainModelCommand(
                family="arima",
                symbol="AAPL",
            )
        )

        first_version = (
            await registry_repo.get_by_id(
                first_result.model_version_id
            )
        )

        assert first_version is not None
        assert first_version.status == "active"

        retrain_use_case = RetrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        second_result = await retrain_use_case.execute(
            TrainModelCommand(
                family="arima",
                symbol="AAPL",
            )
        )

        second_version = (
            await registry_repo.get_by_id(
                second_result.model_version_id
            )
        )

        assert second_version is not None
        assert second_version.status == "active"

        assert (
            second_version.id
            != first_version.id
        )

        previous_version = (
            await registry_repo.get_by_id(
                first_result.model_version_id
            )
        )

        assert previous_version is not None
        assert previous_version.status == "retired"

    async def test_succeeds_when_no_previous_version_exists(
        self,
        tmp_path,
    ) -> None:  # type: ignore[no-untyped-def]

        market_data_repo = (
            FakeMarketDataRepository.with_default_bars(
                synthetic_bars(100)
            )
        )

        registry_repo = (
            FakeModelRegistryRepository()
        )

        use_case = RetrainModelUseCase(
            market_data_repo,
            registry_repo,
            tmp_path,
        )

        result = await use_case.execute(
            TrainModelCommand(
                family="xgboost",
                symbol="AAPL",
            )
        )

        assert result.symbol == "AAPL"
        assert result.family == "xgboost"
        assert result.status == "active"

        active = (
            await registry_repo.get_active_for_family_and_symbol(
                "xgboost",
                "AAPL",
            )
        )

        assert active is not None
        assert active.symbol == "AAPL"
        assert active.status == "active"