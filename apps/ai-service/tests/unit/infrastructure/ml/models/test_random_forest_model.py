"""Unit tests for RandomForestModel. Uses FeatureEngineer to build a
realistic engineered feature matrix, matching how the model is actually
consumed in the decision engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)
from src.infrastructure.ml.models.random_forest_model import (
    MINIMUM_HISTORY_DAYS,
    RandomForestModel,
)


def _ohlcv(n: int = 100, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(loc=0.05, scale=1.0, size=n)
    close = pd.Series(100 + np.cumsum(steps))
    high = close + 1.0
    low = close - 1.0
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(np.full(n, 500_000.0))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


def _training_data(n: int = 100) -> tuple[pd.DataFrame, pd.Series]:
    ohlcv = _ohlcv(n)
    engineer = FeatureEngineer()
    matrix = engineer.build(ohlcv)
    clean_features = FeatureEngineer.handle_missing_values(matrix.raw)
    labels = classification_labels_from_returns(ohlcv["close"], horizon_days=1)
    combined = clean_features.copy()
    combined["_label"] = labels
    combined = combined.dropna()
    y = combined.pop("_label")
    return combined, y


class TestHasSufficientHistory:
    def test_below_minimum_is_false(self) -> None:
        assert RandomForestModel.has_sufficient_history(19) is False

    def test_at_minimum_is_true(self) -> None:
        assert RandomForestModel.has_sufficient_history(20) is True


class TestRandomForestTrain:
    def test_rejects_too_little_data(self) -> None:
        model = RandomForestModel()
        features = pd.DataFrame({"rsi_14": [1.0, 2.0, 3.0]})
        labels = pd.Series([0, 1, 0])
        with pytest.raises(ValueError, match="requires at least"):
            model.train(features, labels)

    def test_rejects_empty_feature_columns(self) -> None:
        model = RandomForestModel()
        features = pd.DataFrame(index=range(MINIMUM_HISTORY_DAYS))
        labels = pd.Series([0] * MINIMUM_HISTORY_DAYS)
        with pytest.raises(ValueError, match="at least one feature column"):
            model.train(features, labels)

    def test_trains_and_returns_metrics_and_importances(self) -> None:
        model = RandomForestModel()
        features, labels = _training_data(100)
        result = model.train(features, labels)
        assert 0.0 <= result.metrics.accuracy <= 1.0
        assert set(result.feature_importances.keys()) == set(features.columns)
        assert all(v >= 0 for v in result.feature_importances.values())


class TestRandomForestPredictMovement:
    def test_raises_if_not_trained(self) -> None:
        model = RandomForestModel()
        features, _ = _training_data(100)
        with pytest.raises(RuntimeError, match="train\\(\\) must be called"):
            model.predict_movement(features.iloc[:1])

    def test_returns_probabilities_in_valid_range(self) -> None:
        model = RandomForestModel()
        features, labels = _training_data(100)
        model.train(features, labels)
        probabilities = model.predict_movement(features.iloc[-5:])
        assert len(probabilities) == 5
        assert ((probabilities >= 0.0) & (probabilities <= 1.0)).all()


class TestRandomForestFeatureImportances:
    def test_raises_if_not_trained(self) -> None:
        model = RandomForestModel()
        with pytest.raises(RuntimeError, match="train\\(\\) must be called"):
            model.feature_importances()

    def test_importances_sum_to_approximately_one(self) -> None:
        model = RandomForestModel()
        features, labels = _training_data(100)
        model.train(features, labels)
        total = sum(model.feature_importances().values())
        assert total == pytest.approx(1.0, abs=0.01)


class TestRandomForestSaveLoad:
    def test_round_trips_and_predicts_identically(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        model = RandomForestModel()
        features, labels = _training_data(100)
        model.train(features, labels)
        before = model.predict_movement(features.iloc[-5:])

        artifact_path = tmp_path / "rf_test.pkl"
        model.save(artifact_path)
        loaded = RandomForestModel.load(artifact_path)
        after = loaded.predict_movement(features.iloc[-5:])

        np.testing.assert_array_almost_equal(before, after)

    def test_save_raises_if_not_trained(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        model = RandomForestModel()
        with pytest.raises(RuntimeError, match="train\\(\\) must be called"):
            model.save(tmp_path / "never_trained.pkl")
