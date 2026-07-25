"""FeatureEngineer — orchestrates the full technical-indicator feature
matrix, missing-value handling, and scaling over an OHLCV DataFrame.

Per Document 4 §10.1a: indicators whose window exceeds the available
history are OMITTED from the feature vector entirely (columns dropped),
not computed on a truncated, non-standard window and silently returned as
if valid — this is the concrete implementation of that gating rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.infrastructure.ml.features import indicators

# (column_name, minimum_rows_required) — mirrors Document 4 §10.1a's
# "SMA200/RSI14/technical indicators: matches indicator's own window"
# gating rule, applied uniformly to every indicator this module computes.
_INDICATOR_MIN_ROWS: dict[str, int] = {
    "sma_20": 20,
    "sma_50": 50,
    "sma_200": 200,
    "ema_12": 12,
    "ema_26": 26,
    "rsi_14": 14,
    "macd_line": 26,
    "macd_signal": 35,
    "macd_histogram": 35,
    "bb_middle": 20,
    "bb_upper": 20,
    "bb_lower": 20,
    "atr_14": 14,
    "vwap": 1,
    "obv": 1,
    "roc_12": 12,
    "adx_14": 28,
}


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    """The result of feature engineering — the raw (unscaled) feature
    DataFrame, the scaled version, and which indicator columns were
    included vs. omitted for gating transparency (feeds
    ExplainabilityPayload.reasoning and the dataQuality decision)."""

    raw: pd.DataFrame
    scaled: pd.DataFrame
    included_columns: tuple[str, ...]
    omitted_columns: tuple[str, ...]


class FeatureEngineer:
    """Builds the engineered feature matrix for one instrument's OHLCV
    history. Stateless except for the fitted scaler, which is recreated
    per call — this phase does not persist a fitted scaler across
    train/serve boundaries (disclosed in known-issues.md; the frozen
    architecture's feature-registry versioning concept, Document 4 §10.2,
    is not built out as a separate shared library this phase — see
    module docstring in src/infrastructure/ml/features/__init__.py)."""

    def build(self, ohlcv: pd.DataFrame) -> FeatureMatrix:
        """`ohlcv` must have columns [open, high, low, close, volume],
        indexed ascending by bar_time. Returns engineered features aligned
        to the same index (rows with insufficient history for ANY
        included indicator are NaN for that indicator's columns, not
        dropped — callers select rows explicitly, e.g. the latest row for
        inference, or drop NaN rows for training)."""
        df = ohlcv.copy()
        n_rows = len(df)

        feature_frames: list[pd.Series | pd.DataFrame] = []

        candidate_columns: dict[str, pd.Series | pd.DataFrame] = {
            "sma_20": indicators.sma(df["close"], 20),
            "sma_50": indicators.sma(df["close"], 50),
            "sma_200": indicators.sma(df["close"], 200),
            "ema_12": indicators.ema(df["close"], 12),
            "ema_26": indicators.ema(df["close"], 26),
            "rsi_14": indicators.rsi(df["close"], 14),
            "atr_14": indicators.atr(df["high"], df["low"], df["close"], 14),
            "vwap": indicators.vwap(df["high"], df["low"], df["close"], df["volume"]),
            "obv": indicators.obv(df["close"], df["volume"]),
            "roc_12": indicators.roc(df["close"], 12),
            "adx_14": indicators.adx(df["high"], df["low"], df["close"], 14),
        }
        macd_df = indicators.macd(df["close"])
        bb_df = indicators.bollinger_bands(df["close"])

        included: list[str] = []
        omitted: list[str] = []

        for name, series in candidate_columns.items():
            min_rows = _INDICATOR_MIN_ROWS[name]
            if n_rows >= min_rows:
                feature_frames.append(series.rename(name))
                included.append(name)
            else:
                omitted.append(name)

        for name in macd_df.columns:
            min_rows = _INDICATOR_MIN_ROWS[str(name)]
            if n_rows >= min_rows:
                feature_frames.append(macd_df[name])
                included.append(str(name))
            else:
                omitted.append(str(name))

        for name in bb_df.columns:
            min_rows = _INDICATOR_MIN_ROWS[str(name)]
            if n_rows >= min_rows:
                feature_frames.append(bb_df[name])
                included.append(str(name))
            else:
                omitted.append(str(name))

        raw = pd.concat(feature_frames, axis=1) if feature_frames else pd.DataFrame(index=df.index)
        scaled = self._scale(raw)

        return FeatureMatrix(
            raw=raw,
            scaled=scaled,
            included_columns=tuple(included),
            omitted_columns=tuple(omitted),
        )

    @staticmethod
    def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
        """Forward-fill then back-fill remaining leading NaNs, matching
        the standard approach for indicator warm-up periods — never
        silently replaced with 0 (which would fabricate a misleading
        signal value for e.g. RSI or MACD)."""
        return df.ffill().bfill()

    @staticmethod
    def _scale(df: pd.DataFrame) -> pd.DataFrame:
        """Z-score normalization (StandardScaler) fitted on non-NaN rows
        only, per-column — NaN rows remain NaN in the scaled output rather
        than being imputed as part of scaling (missing-value handling is a
        separate, explicit step via handle_missing_values(), not silently
        folded into scaling)."""
        if df.empty or df.shape[1] == 0:
            return df.copy()

        scaled = df.copy()
        for column in df.columns:
            series = df[column]
            valid_mask = series.notna()
            if valid_mask.sum() < 2:
                # Not enough non-NaN values to compute a meaningful
                # standard deviation — leave the column unscaled rather
                # than dividing by a near-zero/undefined std.
                continue
            scaler = StandardScaler()
            values = series[valid_mask].to_numpy().reshape(-1, 1)
            scaled_values = scaler.fit_transform(values).flatten()
            scaled.loc[valid_mask, column] = scaled_values
        return scaled

    @staticmethod
    def to_supervised_dataset(
        raw_features: pd.DataFrame, close: pd.Series, horizon_days: int = 1
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Builds (X, y) for a horizon-days-ahead price-direction/price
        target — drops rows with any NaN feature (warm-up period) and the
        final `horizon_days` rows (no future target available yet).
        Shared by the tree-based models (Random Forest, XGBoost)."""
        target = close.shift(-horizon_days)
        combined = raw_features.copy()
        combined["_target"] = target
        combined = combined.dropna()
        y = combined.pop("_target")
        return combined, y


def classification_labels_from_returns(
    close: pd.Series, horizon_days: int = 1
) -> pd.Series:
    """Binary up/down movement label — 1 if the price horizon_days ahead
    is higher than today's close, else 0. Used by Random Forest/XGBoost's
    classification targets (Document 4's 'Predict Upward/Downward
    Movement' and 'Movement Classification' requirements)."""
    future = close.shift(-horizon_days)
    return (future > close).astype(int).where(future.notna(), other=np.nan)
