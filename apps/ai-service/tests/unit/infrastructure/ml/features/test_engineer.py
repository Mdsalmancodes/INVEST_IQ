"""Unit tests for FeatureEngineer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
    classification_labels_from_returns,
)


def _ohlcv(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    steps = rng.normal(loc=0.05, scale=1.0, size=n)
    close = pd.Series(100 + np.cumsum(steps))
    high = close + 1.0
    low = close - 1.0
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(np.full(n, 500_000.0))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestFeatureEngineerBuild:
    def test_omits_indicators_below_minimum_window(self) -> None:
        engineer = FeatureEngineer()
        matrix = engineer.build(_ohlcv(30))
        assert "sma_200" in matrix.omitted_columns
        assert "sma_20" in matrix.included_columns

    def test_includes_all_indicators_with_enough_history(self) -> None:
        engineer = FeatureEngineer()
        matrix = engineer.build(_ohlcv(250))
        assert matrix.omitted_columns == ()
        assert "sma_200" in matrix.included_columns
        assert "adx_14" in matrix.included_columns

    def test_raw_and_scaled_share_the_same_columns(self) -> None:
        engineer = FeatureEngineer()
        matrix = engineer.build(_ohlcv(250))
        assert list(matrix.raw.columns) == list(matrix.scaled.columns)

    def test_scaled_columns_are_roughly_zero_mean(self) -> None:
        engineer = FeatureEngineer()
        matrix = engineer.build(_ohlcv(250))
        # Per-column mean over that column's own valid values — a joint
        # dropna() across all columns would bias the subset toward rows
        # where every indicator happens to be defined, which is a test
        # artifact, not a property of the scaler itself.
        means = matrix.scaled.apply(lambda col: col.dropna().mean())
        assert (means.abs() < 0.5).all()


class TestHandleMissingValues:
    def test_forward_and_back_fills_nans(self) -> None:
        df = pd.DataFrame({"a": [np.nan, np.nan, 1.0, np.nan, 2.0]})
        result = FeatureEngineer.handle_missing_values(df)
        assert not result["a"].isna().any()
        assert result["a"].iloc[0] == 1.0  # back-filled from first valid value
        assert result["a"].iloc[3] == 1.0  # forward-filled from prior valid value


class TestToSupervisedDataset:
    def test_drops_rows_without_a_future_target(self) -> None:
        engineer = FeatureEngineer()
        ohlcv = _ohlcv(250)
        matrix = engineer.build(ohlcv)
        clean_features = FeatureEngineer.handle_missing_values(matrix.raw)
        x, y = FeatureEngineer.to_supervised_dataset(clean_features, ohlcv["close"], horizon_days=5)
        assert len(x) == len(y)
        assert len(x) < len(ohlcv)


class TestClassificationLabelsFromReturns:
    def test_labels_up_movement_as_one(self) -> None:
        close = pd.Series([100.0, 105.0])
        labels = classification_labels_from_returns(close, horizon_days=1)
        assert labels.iloc[0] == 1

    def test_labels_down_movement_as_zero(self) -> None:
        close = pd.Series([100.0, 95.0])
        labels = classification_labels_from_returns(close, horizon_days=1)
        assert labels.iloc[0] == 0

    def test_last_rows_are_nan_without_a_future_price(self) -> None:
        close = pd.Series([100.0, 105.0])
        labels = classification_labels_from_returns(close, horizon_days=1)
        assert pd.isna(labels.iloc[-1])
