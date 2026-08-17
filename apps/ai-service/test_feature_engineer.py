from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pandas as pd

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)
from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
)


async def main() -> None:
    print("=" * 78)
    print("INVEST IQ - FEATURE ENGINEERING TEST")
    print("=" * 78)

    # ========================================================================
    # 1. FETCH REAL MARKET DATA
    # ========================================================================

    repository = MarketDataRepository()

    symbol = "AAPL"

    end = date.today()
    start = end - timedelta(days=400)

    print()
    print(f"Symbol: {symbol}")
    print(f"Start : {start}")
    print(f"End   : {end}")
    print()

    print("📡 Fetching REAL market data...")

    bars = await repository.get_ohlcv_bars(
        symbol,
        start,
        end,
    )

    if not bars:
        raise RuntimeError(
            f"MarketDataRepository returned zero bars for {symbol}."
        )

    print(
        f"✅ REAL OHLCV BARS: {len(bars)}"
    )

    # ========================================================================
    # 2. BUILD CANONICAL OHLCV DATAFRAME
    # ========================================================================

    ohlcv = pd.DataFrame(
        [
            {
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
            for bar in bars
        ],
        index=pd.to_datetime(
            [
                bar.bar_time
                for bar in bars
            ]
        ),
    )

    # Ensure chronological order.
    ohlcv = ohlcv.sort_index()

    print()
    print("=" * 78)
    print("OHLCV DATA")
    print("=" * 78)

    print()
    print("OHLCV SHAPE:")
    print(ohlcv.shape)

    print()
    print("OHLCV COLUMNS:")
    print(list(ohlcv.columns))

    print()
    print("FIRST 5 OHLCV ROWS:")
    print(
        ohlcv.head().to_string()
    )

    print()
    print("LAST 5 OHLCV ROWS:")
    print(
        ohlcv.tail().to_string()
    )

    # ========================================================================
    # 3. BASIC OHLCV VALIDATION
    # ========================================================================

    required_columns = {
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing_columns = (
        required_columns
        - set(ohlcv.columns)
    )

    if missing_columns:
        raise RuntimeError(
            "OHLCV dataframe is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if ohlcv.empty:
        raise RuntimeError(
            "OHLCV dataframe is empty."
        )

    if ohlcv.isna().any().any():
        raise RuntimeError(
            "OHLCV dataframe contains NaN values."
        )

    if (
        ohlcv[
            [
                "open",
                "high",
                "low",
                "close",
            ]
        ]
        <= 0
    ).any().any():
        raise RuntimeError(
            "OHLCV contains non-positive prices."
        )

    if (
        ohlcv["volume"] < 0
    ).any():
        raise RuntimeError(
            "OHLCV contains negative volume."
        )

    print()
    print(
        "✅ BASIC OHLCV VALIDATION PASSED"
    )

    # ========================================================================
    # 4. FEATURE ENGINEERING
    # ========================================================================

    print()
    print("=" * 78)
    print("FEATURE ENGINEERING")
    print("=" * 78)

    engineer = FeatureEngineer()

    feature_matrix = engineer.build(
        ohlcv
    )

    print()
    print("RAW FEATURE SHAPE:")
    print(
        feature_matrix.raw.shape
    )

    print()
    print("SCALED FEATURE SHAPE:")
    print(
        feature_matrix.scaled.shape
    )

    # ========================================================================
    # 5. INCLUDED FEATURES
    # ========================================================================

    print()
    print("INCLUDED FEATURES:")

    for feature in feature_matrix.included_columns:
        print(
            "  ✅",
            feature,
        )

    # ========================================================================
    # 6. OMITTED FEATURES
    # ========================================================================

    print()
    print("OMITTED FEATURES:")

    if feature_matrix.omitted_columns:

        for feature in feature_matrix.omitted_columns:
            print(
                "  ⚪",
                feature,
            )

    else:

        print(
            "  None"
        )

    # ========================================================================
    # 7. RAW FEATURE COLUMNS
    # ========================================================================

    print()
    print("RAW FEATURE COLUMNS:")

    print(
        list(
            feature_matrix.raw.columns
        )
    )

    # ========================================================================
    # 8. LAST FEATURE ROW
    # ========================================================================

    print()
    print("LAST FEATURE ROW:")

    if feature_matrix.raw.empty:
        raise RuntimeError(
            "FeatureEngineer produced an empty raw feature matrix."
        )

    print(
        feature_matrix.raw.tail(1).to_string()
    )

    # ========================================================================
    # 9. CHECK FEATURE NaNs
    # ========================================================================
    #
    # Warm-up rows are expected to contain NaNs for indicators such as:
    #
    #   SMA 200
    #   MACD
    #   ADX
    #
    # We DO NOT backfill these values.
    #
    # The classification dataset builder will remove rows that do not
    # contain valid features.
    # ========================================================================

    print()
    print("RAW FEATURE NaN COUNTS:")

    nan_counts = (
        feature_matrix.raw
        .isna()
        .sum()
    )

    print(
        nan_counts.to_string()
    )

    # ========================================================================
    # 10. BUILD CLASSIFICATION DATASET
    # ========================================================================
    #
    # IMPORTANT:
    #
    # DO NOT USE:
    #
    #     to_supervised_dataset()
    #
    # for Random Forest/XGBoost classification.
    #
    # to_supervised_dataset() produces:
    #
    #     y = future closing price
    #
    # which is a REGRESSION target.
    #
    # Our Random Forest/XGBoost architecture uses:
    #
    #     1 = future close > current close
    #     0 = future close <= current close
    #
    # Therefore we use:
    #
    #     to_classification_dataset()
    #
    # ========================================================================

    print()
    print("=" * 78)
    print("CLASSIFICATION DATASET")
    print("=" * 78)

    features, labels = (
        FeatureEngineer.to_classification_dataset(
            raw_features=feature_matrix.raw,
            close=ohlcv["close"],
            horizon_days=1,
        )
    )

    print()
    print("FEATURE MATRIX:")
    print(
        features.shape
    )

    print()
    print("LABELS:")
    print(
        labels.shape
    )

    # ========================================================================
    # 11. LABEL DISTRIBUTION
    # ========================================================================

    print()
    print("LABEL DISTRIBUTION:")

    print(
        labels.value_counts()
        .sort_index()
        .to_dict()
    )

    # ========================================================================
    # 12. FIRST LABELS
    # ========================================================================

    print()
    print("FIRST 10 LABELS:")

    print(
        labels.head(10).to_string()
    )

    # ========================================================================
    # 13. LAST LABELS
    # ========================================================================

    print()
    print("LAST 10 LABELS:")

    print(
        labels.tail(10).to_string()
    )

    # ========================================================================
    # 14. LABEL MEANING
    # ========================================================================

    print()
    print("LABEL MEANING:")
    print(
        "  1 = future close > current close"
    )
    print(
        "  0 = future close <= current close"
    )

    # ========================================================================
    # 15. DATASET VALIDATION
    # ========================================================================

    if feature_matrix.raw.empty:
        raise RuntimeError(
            "FeatureEngineer produced an empty feature matrix."
        )

    if features.empty:
        raise RuntimeError(
            "Classification feature dataset is empty."
        )

    if labels.empty:
        raise RuntimeError(
            "Classification labels are empty."
        )

    # ------------------------------------------------------------------------
    # Feature/label row count must match.
    # ------------------------------------------------------------------------

    if len(features) != len(labels):
        raise RuntimeError(
            "Feature/label row count mismatch: "
            f"{len(features)} features vs "
            f"{len(labels)} labels."
        )

    # ------------------------------------------------------------------------
    # Only binary classes are allowed.
    # ------------------------------------------------------------------------

    unique_labels = set(
        labels.unique()
    )

    if not unique_labels.issubset(
        {0, 1}
    ):
        raise RuntimeError(
            "Classification labels contain values other than "
            f"0 and 1: {unique_labels}"
        )

    # ------------------------------------------------------------------------
    # Both classes must exist for Random Forest/XGBoost training.
    # ------------------------------------------------------------------------

    if labels.nunique() < 2:
        raise RuntimeError(
            "Only one classification class exists. "
            "Random Forest/XGBoost cannot train correctly."
        )

    # ------------------------------------------------------------------------
    # Feature columns must not contain invalid infinite values.
    # ------------------------------------------------------------------------

    import numpy as np

    feature_values = (
        features.to_numpy(
            dtype=float
        )
    )

    if not np.isfinite(
        feature_values
    ).all():
        raise RuntimeError(
            "Classification feature matrix contains "
            "NaN or infinite values."
        )

    # ------------------------------------------------------------------------
    # Labels must be integer 0/1.
    # ------------------------------------------------------------------------

    if not pd.api.types.is_integer_dtype(
        labels.dtype
    ):
        raise RuntimeError(
            "Classification labels are not integer values."
        )

    # ========================================================================
    # 16. VERIFY NO FUTURE TARGET LEAKAGE
    # ========================================================================
    #
    # For horizon=1:
    #
    # feature row at date t
    # target at date t = close(t+1) > close(t)
    #
    # The final row cannot have a target and therefore must be removed.
    #
    # ========================================================================

    if features.index.max() >= ohlcv.index.max():
        raise RuntimeError(
            "Potential future-target leakage detected: "
            "classification features include the final OHLCV row."
        )

    print()
    print(
        "✅ NO FUTURE TARGET ROW INCLUDED"
    )

    # ========================================================================
    # 17. FINAL SUMMARY
    # ========================================================================

    print()
    print("=" * 78)
    print("FEATURE ENGINEERING SUMMARY")
    print("=" * 78)

    print()
    print(f"Symbol                : {symbol}")
    print(
        f"Real OHLCV bars       : {len(ohlcv)}"
    )
    print(
        f"Technical features    : "
        f"{len(feature_matrix.included_columns)}"
    )
    print(
        f"Omitted features      : "
        f"{len(feature_matrix.omitted_columns)}"
    )
    print(
        f"Classification rows    : "
        f"{len(features)}"
    )
    print(
        f"Classification labels  : "
        f"{len(labels)}"
    )
    print(
        f"Unique labels          : "
        f"{sorted(unique_labels)}"
    )

    print()
    print(
        "LABEL COUNTS:"
    )

    for label, count in (
        labels.value_counts()
        .sort_index()
        .items()
    ):
        direction = (
            "DOWN / SAME"
            if label == 0
            else "UP"
        )

        print(
            f"  {label} ({direction}) : {count}"
        )

    # ========================================================================
    # 18. SUCCESS
    # ========================================================================

    print()
    print("=" * 78)
    print(
        "✅ FEATURE ENGINEERING TEST PASSED"
    )
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())