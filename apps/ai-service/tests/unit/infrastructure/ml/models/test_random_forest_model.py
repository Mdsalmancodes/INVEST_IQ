"""
Unit tests for RandomForestModel.

Uses FeatureEngineer to build a realistic engineered feature matrix,
matching how the model is actually consumed in the decision engine.

The synthetic OHLCV data generated here is structurally valid:

    low <= open
    low <= close
    high >= open
    high >= close

This is important because FeatureEngineer intentionally validates
OHLCV integrity before calculating technical indicators.
"""

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


# ============================================================================
# SYNTHETIC OHLCV
# ============================================================================


def _ohlcv(
    n: int = 100,
    seed: int = 11,
) -> pd.DataFrame:
    """
    Generate deterministic, structurally valid OHLCV data.

    This is test data only.

    The important invariant is:

        high >= max(open, close)
        low  <= min(open, close)
    """

    if n <= 0:
        raise ValueError(
            "n must be greater than zero."
        )

    rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------------

    steps = rng.normal(
        loc=0.05,
        scale=1.0,
        size=n,
    )

    close = pd.Series(
        100.0 + np.cumsum(steps),
        dtype=float,
    )

    # Keep prices strictly positive.
    close = close.clip(
        lower=1.0,
    )

    # ------------------------------------------------------------------------
    # OPEN
    # ------------------------------------------------------------------------

    open_ = (
        close
        .shift(1)
        .fillna(close.iloc[0])
        .astype(float)
    )

    # ------------------------------------------------------------------------
    # HIGH
    # ------------------------------------------------------------------------
    #
    # High must be greater than or equal to BOTH open and close.
    # ------------------------------------------------------------------------

    high = (
        pd.concat(
            [
                open_,
                close,
            ],
            axis=1,
        )
        .max(axis=1)
        + 1.0
    )

    # ------------------------------------------------------------------------
    # LOW
    # ------------------------------------------------------------------------
    #
    # Low must be less than or equal to BOTH open and close.
    # ------------------------------------------------------------------------

    low = (
        pd.concat(
            [
                open_,
                close,
            ],
            axis=1,
        )
        .min(axis=1)
        - 1.0
    )

    # Guarantee strictly positive prices.
    low = low.clip(
        lower=0.01,
    )

    # ------------------------------------------------------------------------
    # VOLUME
    # ------------------------------------------------------------------------

    volume = pd.Series(
        np.full(
            n,
            500_000.0,
        ),
        dtype=float,
    )

    # ------------------------------------------------------------------------
    # DATETIME INDEX
    # ------------------------------------------------------------------------

    index = pd.date_range(
        start="2024-01-01",
        periods=n,
        freq="D",
    )

    return pd.DataFrame(
        {
            "open": open_.to_numpy(dtype=float),
            "high": high.to_numpy(dtype=float),
            "low": low.to_numpy(dtype=float),
            "close": close.to_numpy(dtype=float),
            "volume": volume.to_numpy(dtype=float),
        },
        index=index,
    )


# ============================================================================
# TRAINING DATA
# ============================================================================


def _training_data(
    n: int = 100,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build the same feature representation used by the model pipeline.

    Pipeline:

        OHLCV
          ↓
        FeatureEngineer
          ↓
        Missing-value handling
          ↓
        Classification labels
          ↓
        Clean features + labels
    """

    ohlcv = _ohlcv(n)

    engineer = FeatureEngineer()

    matrix = engineer.build(
        ohlcv,
    )

    clean_features = (
        FeatureEngineer.handle_missing_values(
            matrix.raw,
        )
    )

    labels = classification_labels_from_returns(
        ohlcv["close"],
        horizon_days=1,
    )

    combined = clean_features.copy()

    combined["_label"] = labels

    combined = combined.dropna()

    y = combined.pop(
        "_label",
    )

    y = y.astype(int)

    return combined, y


# ============================================================================
# HISTORY
# ============================================================================


class TestHasSufficientHistory:
    def test_below_minimum_is_false(
        self,
    ) -> None:
        assert (
            RandomForestModel.has_sufficient_history(
                19,
            )
            is False
        )

    def test_at_minimum_is_true(
        self,
    ) -> None:
        assert (
            RandomForestModel.has_sufficient_history(
                MINIMUM_HISTORY_DAYS,
            )
            is True
        )


# ============================================================================
# TRAIN
# ============================================================================


class TestRandomForestTrain:
    def test_rejects_too_little_data(
        self,
    ) -> None:
        model = RandomForestModel()

        features = pd.DataFrame(
            {
                "rsi_14": [
                    1.0,
                    2.0,
                    3.0,
                ],
            }
        )

        labels = pd.Series(
            [
                0,
                1,
                0,
            ]
        )

        with pytest.raises(
            ValueError,
            match="requires at least",
        ):
            model.train(
                features,
                labels,
            )

    def test_rejects_empty_feature_columns(
        self,
    ) -> None:
        model = RandomForestModel()

        features = pd.DataFrame(
            index=range(
                MINIMUM_HISTORY_DAYS,
            )
        )

        labels = pd.Series(
            [0] * MINIMUM_HISTORY_DAYS,
        )

        with pytest.raises(
            ValueError,
            match="non-empty feature dataframe",
        ):
            model.train(
                features,
                labels,
            )

    def test_trains_and_returns_metrics_and_importances(
        self,
    ) -> None:
        model = RandomForestModel()

        features, labels = _training_data(
            100,
        )

        result = model.train(
            features,
            labels,
        )

        assert (
            0.0
            <= result.metrics.accuracy
            <= 1.0
        )

        assert (
            set(result.feature_importances.keys())
            == set(features.columns)
        )

        assert all(
            value >= 0
            for value in result.feature_importances.values()
        )


# ============================================================================
# PREDICT MOVEMENT
# ============================================================================


class TestRandomForestPredictMovement:
    def test_raises_if_not_trained(
        self,
    ) -> None:
        model = RandomForestModel()

        features, _ = _training_data(
            100,
        )

        with pytest.raises(
            RuntimeError,
            match=r"train\(\).*must be called",
        ):
            model.predict_movement(
                features.iloc[:1],
            )

    def test_returns_probabilities_in_valid_range(
        self,
    ) -> None:
        model = RandomForestModel()

        features, labels = _training_data(
            100,
        )

        model.train(
            features,
            labels,
        )

        probabilities = model.predict_movement(
            features.iloc[-5:],
        )

        assert len(probabilities) == 5

        assert (
            (probabilities >= 0.0)
            & (probabilities <= 1.0)
        ).all()


# ============================================================================
# FEATURE IMPORTANCES
# ============================================================================


class TestRandomForestFeatureImportances:
    def test_raises_if_not_trained(
        self,
    ) -> None:
        model = RandomForestModel()

        with pytest.raises(
            RuntimeError,
            match=r"train\(\).*must be called",
        ):
            model.feature_importances()

    def test_importances_sum_to_approximately_one(
        self,
    ) -> None:
        model = RandomForestModel()

        features, labels = _training_data(
            100,
        )

        model.train(
            features,
            labels,
        )

        importances = (
            model.feature_importances()
        )

        total = sum(
            importances.values()
        )

        assert total == pytest.approx(
            1.0,
            abs=0.01,
        )


# ============================================================================
# SAVE / LOAD
# ============================================================================


class TestRandomForestSaveLoad:
    def test_round_trips_and_predicts_identically(
        self,
        tmp_path,
    ) -> None:
        model = RandomForestModel()

        features, labels = _training_data(
            100,
        )

        model.train(
            features,
            labels,
        )

        before = model.predict_movement(
            features.iloc[-5:],
        )

        artifact_path = (
            tmp_path
            / "rf_test.pkl"
        )

        model.save(
            artifact_path,
        )

        assert artifact_path.exists()
        assert artifact_path.is_file()
        assert artifact_path.stat().st_size > 0

        loaded = (
            RandomForestModel.load(
                artifact_path,
            )
        )

        after = loaded.predict_movement(
            features.iloc[-5:],
        )

        np.testing.assert_array_almost_equal(
            before,
            after,
        )

    def test_save_raises_if_not_trained(
        self,
        tmp_path,
    ) -> None:
        model = RandomForestModel()

        with pytest.raises(
            RuntimeError,
            match=r"train\(\).*must be called",
        ):
            model.save(
                tmp_path
                / "never_trained.pkl",
            )