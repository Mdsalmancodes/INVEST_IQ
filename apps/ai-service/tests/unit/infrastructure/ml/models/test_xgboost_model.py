"""
Unit tests for XgboostModel.

Uses FeatureEngineer to build a realistic engineered feature matrix,
mirroring the Random Forest test because both models consume the same
classification feature representation.

The synthetic OHLCV data generated here is structurally valid:

    low <= open
    low <= close
    high >= open
    high >= close
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)
from src.infrastructure.ml.models.xgboost_model import (
    MINIMUM_HISTORY_DAYS,
    XgboostModel,
)


# ============================================================================
# SYNTHETIC OHLCV
# ============================================================================


def _ohlcv(
    n: int = 100,
    seed: int = 13,
) -> pd.DataFrame:
    """
    Generate deterministic, structurally valid OHLCV data.

    Important OHLCV invariants:

        high >= max(open, close)
        low  <= min(open, close)

    This matches FeatureEngineer's validation rules.
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
    Build the same classification dataset used by the actual model pipeline.
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
            XgboostModel.has_sufficient_history(
                19,
            )
            is False
        )

    def test_at_minimum_is_true(
        self,
    ) -> None:
        assert (
            XgboostModel.has_sufficient_history(
                MINIMUM_HISTORY_DAYS,
            )
            is True
        )


# ============================================================================
# TRAIN
# ============================================================================


class TestXgboostTrain:
    def test_rejects_too_little_data(
        self,
    ) -> None:
        model = XgboostModel()

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
        model = XgboostModel()

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
        model = XgboostModel()

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


class TestXgboostPredictMovement:
    def test_raises_if_not_trained(
        self,
    ) -> None:
        model = XgboostModel()

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
        model = XgboostModel()

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
# BUY / SELL PROBABILITIES
# ============================================================================


class TestXgboostPredictBuySellProbabilities:
    def test_buy_and_sell_probabilities_sum_to_one(
        self,
    ) -> None:
        model = XgboostModel()

        features, labels = _training_data(
            100,
        )

        model.train(
            features,
            labels,
        )

        buy_prob, sell_prob = (
            model.predict_buy_sell_probabilities(
                features.iloc[-5:],
            )
        )

        np.testing.assert_array_almost_equal(
            buy_prob + sell_prob,
            np.ones(5),
        )

    def test_matches_predict_movement_for_buy_probability(
        self,
    ) -> None:
        model = XgboostModel()

        features, labels = _training_data(
            100,
        )

        model.train(
            features,
            labels,
        )

        movement = model.predict_movement(
            features.iloc[-5:],
        )

        buy_prob, _ = (
            model.predict_buy_sell_probabilities(
                features.iloc[-5:],
            )
        )

        np.testing.assert_array_almost_equal(
            movement,
            buy_prob,
        )


# ============================================================================
# FEATURE IMPORTANCES
# ============================================================================


class TestXgboostFeatureImportances:
    def test_raises_if_not_trained(
        self,
    ) -> None:
        model = XgboostModel()

        with pytest.raises(
            RuntimeError,
            match=r"train\(\).*must be called",
        ):
            model.feature_importances()

    def test_importances_sum_to_approximately_one(
        self,
    ) -> None:
        model = XgboostModel()

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


class TestXgboostSaveLoad:
    def test_round_trips_and_predicts_identically(
        self,
        tmp_path,
    ) -> None:
        model = XgboostModel()

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
            / "xgb_test.pkl"
        )

        model.save(
            artifact_path,
        )

        assert artifact_path.exists()
        assert artifact_path.is_file()
        assert artifact_path.stat().st_size > 0

        loaded = (
            XgboostModel.load(
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
        model = XgboostModel()

        with pytest.raises(
            RuntimeError,
            match=r"train\(\).*must be called",
        ):
            model.save(
                tmp_path
                / "never_trained.pkl",
            )