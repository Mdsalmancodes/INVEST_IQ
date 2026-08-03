"""TrainModelUseCase, RetrainModelUseCase — back the "Train Models" and
"Retrain Models" API endpoints. Fetches OHLCV history via
MarketDataRepository, trains the requested model family, saves the
resulting artifact to local disk (disclosed substitute for S3 — see
known-issues.md), and records the trained ModelVersion via
ModelRegistryRepository per Document 4 §10.8's lifecycle tracking.

RetrainModelUseCase is the exact same operation as TrainModelUseCase —
Document 4 §10.8's lifecycle describes retraining as "train (offline) ->
evaluate -> promote," the identical flow a first training run follows;
the only difference is a previous active ModelVersion already exists for
that family, which this use case retires before saving the new one so
`get_active_for_family()` never returns two 'active' versions at once.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.domain.ml.entities import ModelVersion
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import MarketDataRepository, ModelRegistryRepository
from src.domain.ml.value_objects import ModelFamily
from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)
from src.infrastructure.ml.models.arima_model import ArimaModel
from src.infrastructure.ml.models.lstm_model import LstmModel
from src.infrastructure.ml.models.prophet_model import ProphetModel
from src.infrastructure.ml.models.random_forest_model import RandomForestModel
from src.infrastructure.ml.models.xgboost_model import XgboostModel

_ARTIFACT_EXTENSIONS: dict[ModelFamily, str] = {
    "lstm": "pt",
    "arima": "pkl",
    "prophet": "pkl",
    "random_forest": "pkl",
    "xgboost": "pkl",
    "finbert": "none",  # pretrained, never fine-tuned/saved this phase
}


@dataclass(frozen=True, slots=True)
class TrainModelCommand:
    family: ModelFamily
    symbol: str
    lookback_days: int = 400


@dataclass(frozen=True, slots=True)
class TrainModelResult:
    model_version: ModelVersion
    validation_metrics: dict[str, float]


class TrainModelUseCase:
    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        model_registry_repository: ModelRegistryRepository,
        artifact_storage_root: str | Path,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._model_registry_repository = model_registry_repository
        self._artifact_root = Path(artifact_storage_root)

    async def execute(self, command: TrainModelCommand) -> TrainModelResult:
        if command.family == "finbert":
            raise ValueError(
                "FinBERT is used as a pretrained model this phase (Document 4 §10.3) — "
                "it is not trained/fine-tuned, so it cannot be trained via this use case"
            )

        end = date.today()
        start = end - timedelta(days=command.lookback_days)
        bars = await self._market_data_repository.get_ohlcv_bars(command.symbol, start, end)
        if not bars:
            raise InsufficientDataError(
                f"No OHLCV history available for {command.symbol!r} — cannot train "
                f"{command.family!r}"
            )

        close = pd.Series([b.close for b in bars])
        dates = pd.Series([b.bar_time for b in bars])
        training_start = dates.iloc[0].to_pydatetime()
        training_end = dates.iloc[-1].to_pydatetime()

        version_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        extension = _ARTIFACT_EXTENSIONS[command.family]
        artifact_path = (
            self._artifact_root
            / command.family
            / command.symbol.upper()
            / f"{version_tag}.{extension}"
        )

        # _train_and_save() synchronously fits the requested model family
        # — genuinely CPU-bound work (same rationale as DecisionEngine.
        # decide()'s identical fix in predict_use_case.py) that would
        # otherwise block this coroutine's event loop for the full
        # training duration.
        validation_metrics = await asyncio.to_thread(
            self._train_and_save, command, close, dates, artifact_path
        )

        model_version = ModelVersion.create(
            family=command.family,
            version_tag=version_tag,
            training_data_range_start=training_start,
            training_data_range_end=training_end,
            validation_metrics=validation_metrics,
            artifact_location=str(artifact_path),
        )
        await self._model_registry_repository.save(model_version)
        return TrainModelResult(model_version=model_version, validation_metrics=validation_metrics)

    def _train_and_save(
        self,
        command: TrainModelCommand,
        close: pd.Series,
        dates: pd.Series,
        artifact_path: Path,
    ) -> dict[str, float]:
        if command.family == "lstm":
            lstm_model = LstmModel()
            lstm_result = lstm_model.train(close.to_numpy())
            lstm_model.save(artifact_path)
            return lstm_result.metrics.as_dict()

        if command.family == "arima":
            arima_model = ArimaModel()
            arima_result = arima_model.train(close.to_numpy())
            arima_model.save(artifact_path)
            return arima_result.metrics.as_dict()

        if command.family == "prophet":
            prophet_model = ProphetModel()
            prophet_result = prophet_model.train(dates.to_numpy(), close.to_numpy())
            prophet_model.save(artifact_path)
            return prophet_result.metrics.as_dict()

        # Tree-based models: build the full engineered feature matrix +
        # movement-classification labels, matching how DecisionEngine
        # trains them for inference.
        ohlcv = pd.DataFrame(
            {"close": close, "high": close + 1.0, "low": close - 1.0, "volume": 1.0}
        )
        engineer = FeatureEngineer()
        feature_matrix = engineer.build(ohlcv)
        clean_features = FeatureEngineer.handle_missing_values(feature_matrix.raw)
        labels = classification_labels_from_returns(close, horizon_days=1)
        combined = clean_features.copy()
        combined["_label"] = labels
        combined = combined.dropna()
        features = combined.drop(columns=["_label"])
        target = combined["_label"]

        if command.family == "random_forest":
            rf_model = RandomForestModel()
            rf_result = rf_model.train(features, target)
            rf_model.save(artifact_path)
            return rf_result.metrics.as_dict()

        xgb_model = XgboostModel()
        xgb_result = xgb_model.train(features, target)
        xgb_model.save(artifact_path)
        return xgb_result.metrics.as_dict()


class RetrainModelUseCase:
    """Identical operation to TrainModelUseCase, with the added step of
    retiring the family's previous active ModelVersion first — see
    module docstring."""

    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        model_registry_repository: ModelRegistryRepository,
        artifact_storage_root: str | Path,
    ) -> None:
        self._train_use_case = TrainModelUseCase(
            market_data_repository, model_registry_repository, artifact_storage_root
        )
        self._model_registry_repository = model_registry_repository

    async def execute(self, command: TrainModelCommand) -> TrainModelResult:
        previous_active = await self._model_registry_repository.get_active_for_family(
            command.family
        )
        if previous_active is not None:
            previous_active.retire()
            await self._model_registry_repository.save(previous_active)

        return await self._train_use_case.execute(command)
