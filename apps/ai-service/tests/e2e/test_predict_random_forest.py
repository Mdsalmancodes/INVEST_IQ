"""
INVEST IQ - REAL RANDOM FOREST INFERENCE E2E TEST

Pipeline:

    REAL Yahoo Finance OHLCV
            ↓
    MarketDataRepository
            ↓
    Canonical OHLCV DataFrame
            ↓
    FeatureEngineer
            ↓
    Active Random Forest ModelVersion
            ↓
    ModelLoader
            ↓
    Random Forest .pkl artifact
            ↓
    Persisted training feature schema
            ↓
    Latest valid feature row
            ↓
    Random Forest inference
            ↓
    P(UP) / P(DOWN)
            ↓
    UP / DOWN / NEUTRAL

Important:

    • REAL market data only
    • NO synthetic OHLCV
    • NO model training
    • Uses the ACTIVE registered model
    • Verifies the persisted feature schema
    • Verifies registry/artifact consistency
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)

from src.infrastructure.ml.features.engineer import (
    FeatureEngineer,
)

from src.infrastructure.ml.model_registry.file_system_model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)

from src.infrastructure.ml.models.random_forest_model import (
    RandomForestModel,
    MINIMUM_HISTORY_DAYS,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILY = "random_forest"

LOOKBACK_DAYS = 400

EXPECTED_FEATURE_COUNT = 17

SIGNAL_EPSILON = 1e-12


# ============================================================================
# PROJECT ROOTS
# ============================================================================

# File location:
#
#   /app/tests/e2e/test_predict_random_forest.py
#
# parents[0] = /app/tests/e2e
# parents[1] = /app/tests
# parents[2] = /app
#
# Therefore:
#
#   SERVICE_ROOT = /app

SERVICE_ROOT = (
    Path(__file__).resolve().parents[2]
)

ARTIFACT_ROOT = (
    SERVICE_ROOT
    / "data"
    / "models"
)

REGISTRY_ROOT = (
    SERVICE_ROOT
    / "data"
    / "model_registry"
)


# ============================================================================
# HELPERS
# ============================================================================


def print_separator() -> None:
    print("=" * 78)


def build_ohlcv_dataframe(
    bars,
) -> pd.DataFrame:
    """
    Convert MarketDataRepository domain bars into the canonical
    OHLCV DataFrame expected by FeatureEngineer.
    """

    rows: list[dict[str, object]] = []

    for bar in bars:
        rows.append(
            {
                "bar_time": bar.bar_time,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
        )

    if not rows:
        raise RuntimeError(
            "MarketDataRepository returned no OHLCV bars."
        )

    dataframe = pd.DataFrame(rows)

    dataframe["bar_time"] = pd.to_datetime(
        dataframe["bar_time"],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=["bar_time"]
    )

    if dataframe.empty:
        raise RuntimeError(
            "All OHLCV timestamps became invalid."
        )

    dataframe = dataframe.sort_values(
        "bar_time"
    )

    dataframe = dataframe.drop_duplicates(
        subset=["bar_time"],
        keep="last",
    )

    dataframe = dataframe.set_index(
        "bar_time"
    )

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    missing = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise RuntimeError(
            f"Canonical OHLCV dataframe is missing: {missing}"
        )

    return dataframe[
        required_columns
    ].copy()


def validate_ohlcv(
    dataframe: pd.DataFrame,
) -> None:
    """
    Strict validation of real OHLCV data.
    """

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if dataframe.empty:
        raise RuntimeError(
            "OHLCV dataframe is empty."
        )

    missing = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise RuntimeError(
            f"OHLCV dataframe is missing columns: {missing}"
        )

    if dataframe.index.has_duplicates:
        raise RuntimeError(
            "OHLCV dataframe contains duplicate timestamps."
        )

    if not dataframe.index.is_monotonic_increasing:
        raise RuntimeError(
            "OHLCV dataframe is not sorted chronologically."
        )

    values = dataframe[
        required_columns
    ].to_numpy(
        dtype=np.float64
    )

    if not np.isfinite(values).all():
        raise RuntimeError(
            "OHLCV dataframe contains NaN or infinite values."
        )

    price_columns = [
        "open",
        "high",
        "low",
        "close",
    ]

    if (
        dataframe[price_columns] <= 0
    ).any().any():
        raise RuntimeError(
            "OHLCV prices must be strictly positive."
        )

    if (
        dataframe["volume"] < 0
    ).any():
        raise RuntimeError(
            "OHLCV volume cannot be negative."
        )

    invalid_high = (
        dataframe["high"]
        < dataframe[
            ["open", "close"]
        ].max(axis=1)
    )

    if invalid_high.any():
        raise RuntimeError(
            "Invalid OHLCV data: high is below "
            "open or close."
        )

    invalid_low = (
        dataframe["low"]
        > dataframe[
            ["open", "close"]
        ].min(axis=1)
    )

    if invalid_low.any():
        raise RuntimeError(
            "Invalid OHLCV data: low is above "
            "open or close."
        )


def validate_feature_matrix(
    feature_matrix,
) -> pd.DataFrame:
    """
    Validate the FeatureEngineer result and return its raw feature matrix.
    """

    raw_features = feature_matrix.raw

    if not isinstance(
        raw_features,
        pd.DataFrame,
    ):
        raise RuntimeError(
            "FeatureEngineer.raw is not a pandas DataFrame."
        )

    if raw_features.empty:
        raise RuntimeError(
            "FeatureEngineer returned an empty feature matrix."
        )

    if raw_features.shape[1] == 0:
        raise RuntimeError(
            "FeatureEngineer returned zero feature columns."
        )

    print(
        f"Raw feature shape: {raw_features.shape}"
    )

    print()
    print("FEATURE COLUMNS")

    for index, column in enumerate(
        raw_features.columns,
        start=1,
    ):
        print(
            f"  {index:02d}. {column}"
        )

    return raw_features


def prepare_latest_features(
    raw_features: pd.DataFrame,
) -> pd.DataFrame:
    """
    Remove indicator warm-up rows without using bfill/ffill.

    Only the latest completely valid row is used for inference.
    """

    valid_features = (
        raw_features
        .dropna(
            how="any"
        )
        .copy()
    )

    if valid_features.empty:
        raise RuntimeError(
            "No valid feature rows remain after "
            "removing indicator warm-up rows."
        )

    values = valid_features.to_numpy(
        dtype=np.float64
    )

    if not np.isfinite(values).all():
        raise RuntimeError(
            "Valid feature matrix still contains "
            "NaN or infinite values."
        )

    latest_features = (
        valid_features
        .tail(1)
        .copy()
    )

    if latest_features.shape[0] != 1:
        raise RuntimeError(
            "Latest feature row must contain exactly one row."
        )

    return latest_features


def validate_feature_schema(
    trained_feature_names,
    current_features: pd.DataFrame,
) -> None:
    """
    Verify exact training/inference feature schema.

    This checks:

        1. schema exists
        2. feature count
        3. feature names
        4. feature order
    """

    trained = tuple(
        trained_feature_names
    )

    current = tuple(
        current_features.columns
    )

    if not trained:
        raise RuntimeError(
            "Loaded Random Forest artifact contains "
            "an empty feature schema."
        )

    print()
    print("TRAINED FEATURE SCHEMA")

    for index, name in enumerate(
        trained,
        start=1,
    ):
        print(
            f"  {index:02d}. {name}"
        )

    print()
    print("CURRENT INFERENCE FEATURE SCHEMA")

    for index, name in enumerate(
        current,
        start=1,
    ):
        print(
            f"  {index:02d}. {name}"
        )

    if len(trained) != len(current):
        raise RuntimeError(
            "Feature count mismatch.\n"
            f"Trained: {len(trained)}\n"
            f"Current: {len(current)}"
        )

    print()
    print("✅ Feature count matches.")

    if set(trained) != set(current):

        missing = [
            name
            for name in trained
            if name not in current
        ]

        unexpected = [
            name
            for name in current
            if name not in trained
        ]

        raise RuntimeError(
            "Feature name mismatch.\n"
            f"Missing: {missing}\n"
            f"Unexpected: {unexpected}"
        )

    print(
        "✅ Feature names match."
    )

    if trained != current:
        raise RuntimeError(
            "Feature order mismatch.\n"
            f"Trained: {trained}\n"
            f"Current: {current}"
        )

    print(
        "✅ Feature order matches."
    )


# ============================================================================
# MAIN
# ============================================================================


async def main() -> None:

    print()
    print_separator()
    print(
        "INVEST IQ - REAL RANDOM FOREST INFERENCE E2E TEST"
    )
    print_separator()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    print()
    print("CONFIGURATION")
    print("-" * 78)

    print(
        f"SYMBOL                 : {SYMBOL}"
    )

    print(
        f"MODEL FAMILY           : {MODEL_FAMILY}"
    )

    print(
        f"LOOKBACK DAYS          : {LOOKBACK_DAYS}"
    )

    print(
        f"EXPECTED FEATURES      : {EXPECTED_FEATURE_COUNT}"
    )

    print(
        f"MODEL MIN HISTORY      : {MINIMUM_HISTORY_DAYS}"
    )

    print(
        f"SERVICE ROOT           : {SERVICE_ROOT}"
    )

    print(
        f"ARTIFACT ROOT          : {ARTIFACT_ROOT}"
    )

    print(
        f"REGISTRY ROOT          : {REGISTRY_ROOT}"
    )

    # ========================================================================
    # 1. MARKET DATA REPOSITORY
    # ========================================================================

    print()
    print_separator()
    print("1. MARKET DATA REPOSITORY")
    print_separator()

    market_data_repository = (
        MarketDataRepository()
    )

    print(
        "✅ MarketDataRepository created."
    )

    # ========================================================================
    # 2. MODEL REGISTRY
    # ========================================================================

    print()
    print_separator()
    print("2. MODEL REGISTRY")
    print_separator()

    registry_repository = (
        FileSystemModelRegistryRepository()
    )

    print(
        "✅ FileSystemModelRegistryRepository created."
    )

    # ========================================================================
    # 3. ACTIVE MODEL LOOKUP
    # ========================================================================

    print()
    print_separator()
    print("3. ACTIVE RANDOM FOREST MODEL LOOKUP")
    print_separator()

    active_model = await (
        registry_repository
        .get_active_for_family_and_symbol(
            MODEL_FAMILY,
            SYMBOL,
        )
    )

    if active_model is None:
        raise RuntimeError(
            f"No active {MODEL_FAMILY} model found for {SYMBOL}."
        )

    print(
        "✅ Active Random Forest model found."
    )

    print(
        f"Family            : {active_model.family}"
    )

    print(
        f"Symbol            : {active_model.symbol}"
    )

    print(
        f"Version           : {active_model.version_tag}"
    )

    print(
        f"Status            : {active_model.status}"
    )

    print(
        f"Artifact          : {active_model.artifact_location}"
    )

    # ========================================================================
    # 4. ACTIVE MODEL VALIDATION
    # ========================================================================

    print()
    print_separator()
    print("4. ACTIVE MODEL VALIDATION")
    print_separator()

    if str(
        active_model.family
    ) != MODEL_FAMILY:
        raise RuntimeError(
            "Active model family mismatch."
        )

    if (
        str(active_model.symbol)
        .upper()
        .strip()
        != SYMBOL
    ):
        raise RuntimeError(
            "Active model symbol mismatch."
        )

    if str(
        active_model.status
    ).lower() != "active":
        raise RuntimeError(
            "Active Random Forest model is not active."
        )

    artifact_path = Path(
        active_model.artifact_location
    ).resolve()

    if not artifact_path.exists():
        raise RuntimeError(
            "Registered Random Forest artifact does not exist:\n"
            f"{artifact_path}"
        )

    if not artifact_path.is_file():
        raise RuntimeError(
            "Registered Random Forest artifact is not a file:\n"
            f"{artifact_path}"
        )

    if artifact_path.suffix.lower() != ".pkl":
        raise RuntimeError(
            "Random Forest artifact must use .pkl extension."
        )

    artifact_size = (
        artifact_path.stat().st_size
    )

    if artifact_size <= 0:
        raise RuntimeError(
            "Random Forest artifact is empty."
        )

    print(
        "✅ Model family verified."
    )

    print(
        "✅ Model symbol verified."
    )

    print(
        "✅ Model status verified."
    )

    print(
        "✅ Registered artifact exists."
    )

    print(
        "✅ Registered artifact is a file."
    )

    print(
        "✅ Artifact extension is .pkl."
    )

    print(
        f"✅ Artifact size: {artifact_size:,} bytes"
    )

    # ========================================================================
    # 5. REAL MARKET DATA
    # ========================================================================

    print()
    print_separator()
    print("5. REAL MARKET DATA")
    print_separator()

    end_date = date.today()

    start_date = (
        end_date
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    print(
        f"Start date: {start_date}"
    )

    print(
        f"End date  : {end_date}"
    )

    print()
    print(
        "📡 Fetching REAL Yahoo Finance market data..."
    )

    bars = await (
        market_data_repository
        .get_ohlcv_bars(
            symbol=SYMBOL,
            start=start_date,
            end=end_date,
            interval="1d",
        )
    )

    if not bars:
        raise RuntimeError(
            "No real OHLCV bars were returned."
        )

    print(
        f"✅ Received {len(bars)} real OHLCV bars."
    )

    if len(bars) < MINIMUM_HISTORY_DAYS:
        raise RuntimeError(
            f"Random Forest requires at least "
            f"{MINIMUM_HISTORY_DAYS} rows. "
            f"Received {len(bars)}."
        )

    # ========================================================================
    # 6. OHLCV DATAFRAME
    # ========================================================================

    print()
    print_separator()
    print("6. OHLCV DATAFRAME")
    print_separator()

    ohlcv = build_ohlcv_dataframe(
        bars
    )

    validate_ohlcv(
        ohlcv
    )

    print(
        "✅ OHLCV validation passed."
    )

    print(
        f"Rows       : {len(ohlcv)}"
    )

    print(
        f"Columns    : {list(ohlcv.columns)}"
    )

    print(
        f"First date : {ohlcv.index[0]}"
    )

    print(
        f"Last date  : {ohlcv.index[-1]}"
    )

    print()
    print("LATEST OHLCV BAR")

    print(
        ohlcv.tail(1).to_string()
    )

    # ========================================================================
    # 7. FEATURE ENGINEERING
    # ========================================================================

    print()
    print_separator()
    print("7. FEATURE ENGINEERING")
    print_separator()

    engineer = FeatureEngineer()

    feature_matrix = engineer.build(
        ohlcv
    )

    raw_features = validate_feature_matrix(
        feature_matrix
    )

    print()
    print(
        f"Included features: "
        f"{len(feature_matrix.included_columns)}"
    )

    print(
        f"Omitted features : "
        f"{len(feature_matrix.omitted_columns)}"
    )

    # ========================================================================
    # 8. FEATURE PREPARATION
    # ========================================================================

    print()
    print_separator()
    print("8. INFERENCE FEATURE PREPARATION")
    print_separator()

    latest_features = prepare_latest_features(
        raw_features
    )

    if latest_features.shape[1] != EXPECTED_FEATURE_COUNT:
        raise RuntimeError(
            "FeatureEngineer produced an unexpected "
            f"feature count.\n"
            f"Expected: {EXPECTED_FEATURE_COUNT}\n"
            f"Actual: {latest_features.shape[1]}"
        )

    print(
        "✅ Expected technical feature count verified."
    )

    print(
        f"Valid feature rows : "
        f"{len(raw_features.dropna())}"
    )

    print(
        f"Latest feature date: "
        f"{latest_features.index[-1]}"
    )

    print(
        f"Latest feature shape: "
        f"{latest_features.shape}"
    )

    print()
    print("LATEST FEATURE ROW")

    print(
        latest_features.to_string()
    )

    # ========================================================================
    # 9. MODEL LOADER
    # ========================================================================

    print()
    print_separator()
    print("9. MODEL LOADER")
    print_separator()

    model_loader = ModelLoader(
        model_registry_repository=(
            registry_repository
        ),
        artifact_root=ARTIFACT_ROOT,
    )

    print(
        "✅ ModelLoader created."
    )

    # ========================================================================
    # 10. LOAD ACTIVE MODEL
    # ========================================================================

    print()
    print_separator()
    print("10. LOAD ACTIVE RANDOM FOREST")
    print_separator()

    print(
        "📦 Loading active Random Forest artifact..."
    )

    model = await (
        model_loader.load_model(
            family=MODEL_FAMILY,
            symbol=SYMBOL,
        )
    )

    if model is None:
        raise RuntimeError(
            "ModelLoader returned None."
        )

    if not isinstance(
        model,
        RandomForestModel,
    ):
        raise RuntimeError(
            "ModelLoader returned unexpected type: "
            f"{type(model).__name__}"
        )

    print(
        "✅ Random Forest artifact loaded."
    )

    print(
        f"Loaded model type: "
        f"{type(model).__name__}"
    )

    # ========================================================================
    # 11. MODEL FIT VALIDATION
    # ========================================================================

    print()
    print_separator()
    print("11. RANDOM FOREST MODEL VALIDATION")
    print_separator()

    is_fitted = getattr(
        model,
        "_is_fitted",
        False,
    )

    if not is_fitted:
        raise RuntimeError(
            "Loaded Random Forest model is not fitted."
        )

    print(
        "✅ Random Forest model is fitted."
    )

    # ========================================================================
    # 12. FEATURE SCHEMA VERIFICATION
    # ========================================================================

    print()
    print_separator()
    print("12. FEATURE SCHEMA VERIFICATION")
    print_separator()

    trained_feature_names = getattr(
        model,
        "_feature_names",
        (),
    )

    validate_feature_schema(
        trained_feature_names,
        latest_features,
    )

    print()
    print(
        f"✅ Training schema contains "
        f"{len(trained_feature_names)} features."
    )

    if len(trained_feature_names) != EXPECTED_FEATURE_COUNT:
        raise RuntimeError(
            "Registered Random Forest artifact does not "
            f"contain {EXPECTED_FEATURE_COUNT} features.\n"
            f"Actual: {len(trained_feature_names)}"
        )

    print(
        "✅ Artifact feature count is 17."
    )

    # ========================================================================
    # 13. RANDOM FOREST INFERENCE
    # ========================================================================

    print()
    print_separator()
    print("13. RANDOM FOREST PREDICTION")
    print_separator()

    print(
        "🧠 Running Random Forest inference..."
    )

    probability_up_array = (
        model.predict_movement(
            latest_features
        )
    )

    probability_up_array = np.asarray(
        probability_up_array,
        dtype=np.float64,
    ).reshape(-1)

    if probability_up_array.size != 1:
        raise RuntimeError(
            "Random Forest returned an unexpected "
            "number of probabilities."
        )

    probability_up = float(
        probability_up_array[0]
    )

    if not np.isfinite(
        probability_up
    ):
        raise RuntimeError(
            "Random Forest UP probability is not finite."
        )

    probability_down = (
        1.0
        - probability_up
    )

    if not np.isfinite(
        probability_down
    ):
        raise RuntimeError(
            "Random Forest DOWN probability is not finite."
        )

    # ========================================================================
    # 14. MOVEMENT SIGNAL
    # ========================================================================

    if (
        probability_up
        > probability_down + SIGNAL_EPSILON
    ):
        signal = "UP"

    elif (
        probability_down
        > probability_up + SIGNAL_EPSILON
    ):
        signal = "DOWN"

    else:
        signal = "NEUTRAL"

    # ========================================================================
    # 15. OUTPUT
    # ========================================================================

    current_price = float(
        ohlcv["close"].iloc[-1]
    )

    latest_market_date = (
        ohlcv.index[-1]
    )

    print()
    print("LATEST MARKET INFORMATION")

    print(
        f"Trading date       : "
        f"{latest_market_date}"
    )

    print(
        f"Latest close       : "
        f"{current_price:.4f}"
    )

    print()
    print("RANDOM FOREST OUTPUT")

    print(
        f"Probability UP     : "
        f"{probability_up:.6f}"
    )

    print(
        f"Probability DOWN   : "
        f"{probability_down:.6f}"
    )

    print(
        f"Probability UP %   : "
        f"{probability_up * 100:.2f}%"
    )

    print(
        f"Probability DOWN % : "
        f"{probability_down * 100:.2f}%"
    )

    print(
        f"Movement signal    : "
        f"{signal}"
    )

    # ========================================================================
    # 16. PREDICTION VALIDATION
    # ========================================================================

    print()
    print_separator()
    print("16. PREDICTION VALIDATION")
    print_separator()

    if not (
        0.0 <= probability_up <= 1.0
    ):
        raise RuntimeError(
            f"UP probability outside [0, 1]: "
            f"{probability_up}"
        )

    print(
        "✅ UP probability is valid."
    )

    if not (
        0.0 <= probability_down <= 1.0
    ):
        raise RuntimeError(
            f"DOWN probability outside [0, 1]: "
            f"{probability_down}"
        )

    print(
        "✅ DOWN probability is valid."
    )

    probability_sum = (
        probability_up
        + probability_down
    )

    if not np.isclose(
        probability_sum,
        1.0,
        atol=1e-6,
    ):
        raise RuntimeError(
            "UP + DOWN probabilities do not sum to 1.\n"
            f"UP: {probability_up}\n"
            f"DOWN: {probability_down}\n"
            f"SUM: {probability_sum}"
        )

    print(
        "✅ UP + DOWN probabilities sum to 1."
    )

    if signal not in {
        "UP",
        "DOWN",
        "NEUTRAL",
    }:
        raise RuntimeError(
            f"Invalid movement signal: {signal}"
        )

    print(
        "✅ Movement signal is valid."
    )

    # ========================================================================
    # 17. REGISTRY / ARTIFACT CONSISTENCY
    # ========================================================================

    print()
    print_separator()
    print("17. REGISTRY / ARTIFACT CONSISTENCY")
    print_separator()

    registered_again = await (
        registry_repository
        .get_by_id(
            active_model.id
        )
    )

    if registered_again is None:
        raise RuntimeError(
            "Active Random Forest ModelVersion "
            "could not be retrieved by ID."
        )

    if registered_again.id != active_model.id:
        raise RuntimeError(
            "Registry ID mismatch."
        )

    if registered_again.family != active_model.family:
        raise RuntimeError(
            "Registry family mismatch."
        )

    if registered_again.symbol != active_model.symbol:
        raise RuntimeError(
            "Registry symbol mismatch."
        )

    if registered_again.version_tag != active_model.version_tag:
        raise RuntimeError(
            "Registry version mismatch."
        )

    if registered_again.status != active_model.status:
        raise RuntimeError(
            "Registry status mismatch."
        )

    if (
        Path(
            registered_again.artifact_location
        ).resolve()
        != artifact_path
    ):
        raise RuntimeError(
            "Registry artifact location mismatch."
        )

    print(
        "✅ Registry ID is consistent."
    )

    print(
        "✅ Registry family is consistent."
    )

    print(
        "✅ Registry symbol is consistent."
    )

    print(
        "✅ Registry version is consistent."
    )

    print(
        "✅ Registry status is consistent."
    )

    print(
        "✅ Registry artifact location is consistent."
    )

    print()
    print(
        f"Version : {active_model.version_tag}"
    )

    print(
        f"Artifact: {artifact_path}"
    )

    # ========================================================================
    # 18. FINAL PIPELINE
    # ========================================================================

    print()
    print_separator()
    print("18. FINAL RANDOM FOREST INFERENCE PIPELINE")
    print_separator()

    print()
    print("REAL AAPL MARKET DATA")
    print("        ↓")
    print("MARKET DATA REPOSITORY")
    print("        ↓")
    print("CANONICAL OHLCV DATAFRAME")
    print("        ↓")
    print("FEATURE ENGINEERING")
    print("        ↓")
    print("17 TECHNICAL FEATURES")
    print("        ↓")
    print("ACTIVE MODEL REGISTRY")
    print("        ↓")
    print("MODEL LOADER")
    print("        ↓")
    print("RANDOM FOREST .PKL ARTIFACT")
    print("        ↓")
    print("PERSISTED FEATURE SCHEMA")
    print("        ↓")
    print("LATEST VALID FEATURE ROW")
    print("        ↓")
    print("P(UP) / P(DOWN)")
    print("        ↓")
    print("UP / DOWN / NEUTRAL")

    # ========================================================================
    # FINAL RESULT
    # ========================================================================

    print()
    print_separator()
    print(
        "🎉 RANDOM FOREST REAL INFERENCE E2E TEST PASSED"
    )
    print_separator()

    print()
    print(
        "✅ REAL AAPL MARKET DATA USED"
    )

    print(
        "✅ ACTIVE RANDOM FOREST MODEL FOUND"
    )

    print(
        "✅ REGISTERED ARTIFACT EXISTS"
    )

    print(
        "✅ RANDOM FOREST ARTIFACT LOADED"
    )

    print(
        "✅ RANDOM FOREST MODEL IS FITTED"
    )

    print(
        "✅ FEATURE ENGINEERING COMPLETED"
    )

    print(
        "✅ 17 TECHNICAL FEATURES VERIFIED"
    )

    print(
        "✅ TRAINING FEATURE SCHEMA VERIFIED"
    )

    print(
        "✅ FEATURE ORDER VERIFIED"
    )

    print(
        "✅ LATEST VALID FEATURE ROW CREATED"
    )

    print(
        "✅ REAL RANDOM FOREST PREDICTION GENERATED"
    )

    print(
        "✅ UP/DOWN PROBABILITIES VERIFIED"
    )

    print(
        "✅ MOVEMENT SIGNAL VERIFIED"
    )

    print(
        "✅ REGISTRY/ARTIFACT CONSISTENCY VERIFIED"
    )

    print()
    print(
        "🚀 INVEST IQ RANDOM FOREST IS NOW"
    )

    print(
        "   TRAINED + REGISTERED + LOADABLE + PREDICTING"
    )

    print_separator()
# ============================================================================
# PYTEST ENTRY POINT
# ============================================================================

import pytest


@pytest.mark.slow
def test_random_forest_real_inference_end_to_end() -> None:
    """
    Pytest entry point for the real Random Forest inference E2E test.

    The actual asynchronous workflow is implemented in main().
    """

    asyncio.run(main())


# ============================================================================
# DIRECT SCRIPT ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    asyncio.run(main())