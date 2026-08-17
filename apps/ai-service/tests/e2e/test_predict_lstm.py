"""
INVEST IQ - REAL LSTM INFERENCE E2E TEST

End-to-end verification:

    Real Yahoo Finance OHLCV
            ↓
    MarketDataRepository
            ↓
    Real closing-price history
            ↓
    Active Model Registry
            ↓
    Active LSTM ModelVersion
            ↓
    LSTM .pt artifact
            ↓
    ModelLoader
            ↓
    LstmModel
            ↓
    Latest LSTM lookback window
            ↓
    LSTM inference
            ↓
    1-day forecast
            ↓
    5-day recursive forecast
            ↓
    UP / DOWN / FLAT signal

No mock market data is used.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)

from src.infrastructure.ml.model_registry.file_system_model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)

from src.infrastructure.ml.models.lstm_model import (
    LstmModel,
    LOOKBACK_WINDOW,
)


pytestmark = pytest.mark.slow


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILY = "lstm"

LOOKBACK_DAYS = 400

FORECAST_STEPS = 5

# test file:
# /app/tests/e2e/test_predict_lstm.py
#
# parents[0] = /app/tests/e2e
# parents[1] = /app/tests
# parents[2] = /app
SERVICE_ROOT = Path(__file__).resolve().parents[2]

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


def bars_to_dataframe(
    bars,
) -> pd.DataFrame:
    """
    Convert domain OHLCV bars into a validated DataFrame.
    """

    if not bars:
        raise RuntimeError(
            "No OHLCV bars were returned."
        )

    rows = []

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

    df = pd.DataFrame(rows)

    if df.empty:
        raise RuntimeError(
            "OHLCV dataframe is empty."
        )

    df["bar_time"] = pd.to_datetime(
        df["bar_time"],
        errors="coerce",
    )

    if df["bar_time"].isna().any():
        raise RuntimeError(
            "OHLCV dataframe contains invalid timestamps."
        )

    df = (
        df
        .sort_values("bar_time")
        .drop_duplicates(
            subset=["bar_time"],
            keep="last",
        )
        .set_index("bar_time")
    )

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    return df[required_columns]


def validate_ohlcv(
    df: pd.DataFrame,
) -> None:
    """
    Validate real OHLCV market data.
    """

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    # ------------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------------

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"OHLCV dataframe is missing columns: {missing}"
        )

    # ------------------------------------------------------------------------
    # Empty
    # ------------------------------------------------------------------------

    if df.empty:
        raise RuntimeError(
            "OHLCV dataframe is empty."
        )

    # ------------------------------------------------------------------------
    # NaN
    # ------------------------------------------------------------------------

    if df[required_columns].isna().any().any():
        raise RuntimeError(
            "OHLCV dataframe contains NaN values."
        )

    # ------------------------------------------------------------------------
    # Numeric validity
    # ------------------------------------------------------------------------

    values = df[
        required_columns
    ].to_numpy(
        dtype=np.float64
    )

    if not np.isfinite(values).all():
        raise RuntimeError(
            "OHLCV dataframe contains "
            "NaN or infinite numeric values."
        )

    # ------------------------------------------------------------------------
    # Close prices
    # ------------------------------------------------------------------------

    if (df["close"] <= 0).any():
        raise RuntimeError(
            "OHLCV close prices must be positive."
        )

    # ------------------------------------------------------------------------
    # Volume
    # ------------------------------------------------------------------------

    if (df["volume"] < 0).any():
        raise RuntimeError(
            "OHLCV volume cannot be negative."
        )

    # ------------------------------------------------------------------------
    # High / Low consistency
    # ------------------------------------------------------------------------

    invalid_high = (
        df["high"]
        < df[
            ["open", "close"]
        ].max(axis=1)
    )

    if invalid_high.any():
        raise RuntimeError(
            "Invalid OHLCV data: "
            "high is below open or close."
        )

    invalid_low = (
        df["low"]
        > df[
            ["open", "close"]
        ].min(axis=1)
    )

    if invalid_low.any():
        raise RuntimeError(
            "Invalid OHLCV data: "
            "low is above open or close."
        )


def validate_forecast(
    forecast,
    expected_steps: int,
    name: str,
) -> np.ndarray:
    """
    Validate an LSTM forecast and return a float64 numpy array.
    """

    if forecast is None:
        raise RuntimeError(
            f"{name} returned None."
        )

    forecast_array = np.asarray(
        forecast,
        dtype=np.float64,
    ).reshape(-1)

    if len(forecast_array) != expected_steps:
        raise RuntimeError(
            f"{name} returned {len(forecast_array)} "
            f"values; expected {expected_steps}."
        )

    if not np.isfinite(forecast_array).all():
        raise RuntimeError(
            f"{name} contains NaN or infinite values."
        )

    if (forecast_array <= 0).any():
        raise RuntimeError(
            f"{name} contains non-positive prices."
        )

    return forecast_array


# ============================================================================
# MAIN
# ============================================================================


async def main() -> None:

    print()
    print("=" * 78)
    print("INVEST IQ - REAL LSTM INFERENCE E2E TEST")
    print("=" * 78)

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    print()
    print("CONFIGURATION")
    print("-" * 78)

    print(
        f"SYMBOL          : {SYMBOL}"
    )

    print(
        f"MODEL FAMILY    : {MODEL_FAMILY}"
    )

    print(
        f"LOOKBACK DAYS   : {LOOKBACK_DAYS}"
    )

    print(
        f"LSTM WINDOW     : {LOOKBACK_WINDOW}"
    )

    print(
        f"FORECAST STEPS  : {FORECAST_STEPS}"
    )

    print(
        f"SERVICE ROOT    : {SERVICE_ROOT}"
    )

    print(
        f"ARTIFACT ROOT   : {ARTIFACT_ROOT}"
    )

    print(
        f"REGISTRY ROOT   : {REGISTRY_ROOT}"
    )

    # =========================================================================
    # 1. MARKET DATA REPOSITORY
    # =========================================================================

    print()
    print("=" * 78)
    print("1. MARKET DATA REPOSITORY")
    print("=" * 78)

    market_data_repository = (
        MarketDataRepository()
    )

    print(
        "✅ MarketDataRepository created."
    )

    # =========================================================================
    # 2. MODEL REGISTRY
    # =========================================================================

    print()
    print("=" * 78)
    print("2. MODEL REGISTRY")
    print("=" * 78)

    registry_repository = (
        FileSystemModelRegistryRepository()
    )

    print(
        "✅ FileSystemModelRegistryRepository created."
    )

    # =========================================================================
    # 3. ACTIVE LSTM MODEL LOOKUP
    # =========================================================================

    print()
    print("=" * 78)
    print("3. ACTIVE LSTM MODEL LOOKUP")
    print("=" * 78)

    active_model = await (
        registry_repository
        .get_active_for_family_and_symbol(
            MODEL_FAMILY,
            SYMBOL,
        )
    )

    if active_model is None:
        raise RuntimeError(
            "❌ No active LSTM model found for AAPL."
        )

    print(
        "✅ Active LSTM model found."
    )

    print(
        f"Family            : "
        f"{active_model.family}"
    )

    print(
        f"Symbol            : "
        f"{active_model.symbol}"
    )

    print(
        f"Version           : "
        f"{active_model.version_tag}"
    )

    print(
        f"Status            : "
        f"{active_model.status}"
    )

    print(
        f"Artifact          : "
        f"{active_model.artifact_location}"
    )

    # =========================================================================
    # 4. ACTIVE MODEL VALIDATION
    # =========================================================================

    print()
    print("=" * 78)
    print("4. ACTIVE MODEL VALIDATION")
    print("=" * 78)

    if active_model.family != MODEL_FAMILY:
        raise RuntimeError(
            "❌ Active model family mismatch."
        )

    print(
        "✅ Model family verified."
    )

    if active_model.symbol.upper().strip() != SYMBOL:
        raise RuntimeError(
            "❌ Active model symbol mismatch."
        )

    print(
        "✅ Model symbol verified."
    )

    if active_model.status != "active":
        raise RuntimeError(
            "❌ LSTM model is not active."
        )

    print(
        "✅ Model status verified."
    )

    artifact_path = Path(
        active_model.artifact_location
    )

    if not artifact_path.exists():
        raise RuntimeError(
            "❌ Registered LSTM artifact does not exist."
        )

    print(
        "✅ Registered artifact exists."
    )

    if not artifact_path.is_file():
        raise RuntimeError(
            "❌ Registered LSTM artifact is not a file."
        )

    print(
        "✅ Registered artifact is a file."
    )

    artifact_size = artifact_path.stat().st_size

    if artifact_size <= 0:
        raise RuntimeError(
            "❌ LSTM artifact is empty."
        )

    print(
        f"✅ Artifact size: "
        f"{artifact_size:,} bytes"
    )

    if artifact_path.suffix.lower() != ".pt":
        raise RuntimeError(
            "❌ LSTM artifact must use .pt extension."
        )

    print(
        "✅ Artifact extension is .pt."
    )

    # =========================================================================
    # 5. REAL MARKET DATA
    # =========================================================================

    print()
    print("=" * 78)
    print("5. REAL MARKET DATA")
    print("=" * 78)

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
        "📡 Fetching REAL market data..."
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
            "❌ No real OHLCV bars received."
        )

    print(
        f"✅ Received {len(bars)} "
        "REAL OHLCV bars."
    )

    if len(bars) < LOOKBACK_WINDOW:
        raise RuntimeError(
            f"❌ LSTM requires at least "
            f"{LOOKBACK_WINDOW} market bars. "
            f"Received {len(bars)}."
        )

    # =========================================================================
    # 6. OHLCV DATAFRAME
    # =========================================================================

    print()
    print("=" * 78)
    print("6. OHLCV DATAFRAME")
    print("=" * 78)

    df = bars_to_dataframe(
        bars
    )

    validate_ohlcv(
        df
    )

    print(
        "✅ OHLCV validation passed."
    )

    print(
        f"Rows       : {len(df)}"
    )

    print(
        f"Columns    : {list(df.columns)}"
    )

    print(
        f"First date : {df.index.min()}"
    )

    print(
        f"Last date  : {df.index.max()}"
    )

    print()
    print(
        "LATEST OHLCV BAR"
    )

    print(
        df.iloc[
            [-1]
        ].to_string()
    )

    # =========================================================================
    # 7. REAL CLOSE PRICE HISTORY
    # =========================================================================

    print()
    print("=" * 78)
    print("7. LSTM INPUT PREPARATION")
    print("=" * 78)

    close_prices = (
        df["close"]
        .to_numpy(
            dtype=np.float64
        )
    )

    if len(close_prices) < LOOKBACK_WINDOW:
        raise RuntimeError(
            f"❌ LSTM requires at least "
            f"{LOOKBACK_WINDOW} close prices. "
            f"Received {len(close_prices)}."
        )

    if not np.isfinite(close_prices).all():
        raise RuntimeError(
            "❌ Close-price history contains "
            "NaN or infinite values."
        )

    if (close_prices <= 0).any():
        raise RuntimeError(
            "❌ Close-price history contains "
            "non-positive values."
        )

    print(
        f"Total close prices : "
        f"{len(close_prices)}"
    )

    print(
        f"LSTM window        : "
        f"{LOOKBACK_WINDOW}"
    )

    print(
        f"Latest close       : "
        f"{close_prices[-1]:.4f}"
    )

    latest_window = close_prices[
        -LOOKBACK_WINDOW:
    ]

    if len(latest_window) != LOOKBACK_WINDOW:
        raise RuntimeError(
            "❌ Incorrect LSTM input window length."
        )

    print(
        f"✅ Latest {LOOKBACK_WINDOW}-price "
        "input window verified."
    )

    print()
    print(
        f"LATEST {LOOKBACK_WINDOW} CLOSE PRICES"
    )

    for index, price in enumerate(
        latest_window,
        start=1,
    ):
        print(
            f"{index:02d}. {price:.6f}"
        )

    # =========================================================================
    # 8. MODEL LOADER
    # =========================================================================

    print()
    print("=" * 78)
    print("8. MODEL LOADER")
    print("=" * 78)

    model_loader = ModelLoader(
        model_registry_repository=(
            registry_repository
        ),
        artifact_root=ARTIFACT_ROOT,
    )

    print(
        "✅ ModelLoader created."
    )

    # =========================================================================
    # 9. LOAD ACTIVE LSTM
    # =========================================================================

    print()
    print("=" * 78)
    print("9. LOAD ACTIVE LSTM")
    print("=" * 78)

    print(
        "📦 Loading active LSTM artifact..."
    )

    model = await (
        model_loader.load_model(
            family=MODEL_FAMILY,
            symbol=SYMBOL,
        )
    )

    if model is None:
        raise RuntimeError(
            "❌ ModelLoader returned None "
            "for active LSTM."
        )

    print(
        "✅ LSTM artifact loaded."
    )

    print(
        f"Loaded model type: "
        f"{type(model).__name__}"
    )

    if not isinstance(
        model,
        LstmModel,
    ):
        raise RuntimeError(
            "❌ Loaded model is not "
            "an LstmModel instance."
        )

    print(
        "✅ Loaded model is an LstmModel."
    )

    lstm_model = model

    # =========================================================================
    # 10. LSTM MODEL VALIDATION
    # =========================================================================

    print()
    print("=" * 78)
    print("10. LSTM MODEL VALIDATION")
    print("=" * 78)

    if not lstm_model.is_fitted:
        raise RuntimeError(
            "❌ Loaded LSTM model is not fitted."
        )

    print(
        "✅ LSTM model is fitted."
    )

    if not lstm_model.has_sufficient_history(
        len(close_prices)
    ):
        raise RuntimeError(
            "❌ Close-price history does not satisfy "
            "LSTM minimum history requirement."
        )

    print(
        "✅ LSTM history requirement is valid."
    )

    # =========================================================================
    # 11. ONE-DAY LSTM FORECAST
    # =========================================================================

    print()
    print("=" * 78)
    print("11. ONE-DAY LSTM FORECAST")
    print("=" * 78)

    print(
        "🧠 Running one-step LSTM inference..."
    )

    current_price = float(
        close_prices[-1]
    )

    one_day_forecast = (
        lstm_model.predict_next(
            recent_close_prices=close_prices,
            steps_ahead=1,
        )
    )

    one_day_array = validate_forecast(
        one_day_forecast,
        expected_steps=1,
        name="LSTM one-day forecast",
    )

    next_price = float(
        one_day_array[0]
    )

    expected_change = (
        next_price
        - current_price
    )

    expected_change_percent = (
        expected_change
        / current_price
        * 100.0
    )

    if expected_change > 0:
        movement_signal = "UP"

    elif expected_change < 0:
        movement_signal = "DOWN"

    else:
        movement_signal = "FLAT"

    print()
    print(
        "LATEST MARKET INFORMATION"
    )

    print(
        f"Trading date        : "
        f"{df.index[-1]}"
    )

    print(
        f"Latest close        : "
        f"{current_price:.4f}"
    )

    print()
    print(
        "LSTM OUTPUT"
    )

    print(
        f"Next predicted price: "
        f"{next_price:.4f}"
    )

    print(
        f"Expected change     : "
        f"{expected_change:+.4f}"
    )

    print(
        f"Expected change %   : "
        f"{expected_change_percent:+.2f}%"
    )

    print(
        f"Movement signal     : "
        f"{movement_signal}"
    )

    # =========================================================================
    # 12. FIVE-DAY LSTM FORECAST
    # =========================================================================

    print()
    print("=" * 78)
    print(
        f"12. {FORECAST_STEPS}-DAY LSTM FORECAST"
    )
    print("=" * 78)

    print(
        f"🧠 Generating {FORECAST_STEPS}-step "
        "recursive LSTM forecast..."
    )

    forecasts = (
        lstm_model.predict_next(
            recent_close_prices=close_prices,
            steps_ahead=FORECAST_STEPS,
        )
    )

    forecast_array = validate_forecast(
        forecasts,
        expected_steps=FORECAST_STEPS,
        name="LSTM multi-step forecast",
    )

    print()

    previous_price = current_price

    for step, predicted_price in enumerate(
        forecast_array,
        start=1,
    ):

        predicted_price = float(
            predicted_price
        )

        change_from_current = (
            predicted_price
            - current_price
        )

        change_from_current_percent = (
            change_from_current
            / current_price
            * 100.0
        )

        step_change = (
            predicted_price
            - previous_price
        )

        print(
            f"Day +{step}: "
            f"{predicted_price:.4f} | "
            f"change from current: "
            f"{change_from_current:+.4f} "
            f"({change_from_current_percent:+.2f}%) | "
            f"step change: "
            f"{step_change:+.4f}"
        )

        previous_price = predicted_price

    # =========================================================================
    # 13. FORECAST VALIDATION
    # =========================================================================

    print()
    print("=" * 78)
    print("13. FORECAST VALIDATION")
    print("=" * 78)

    if len(one_day_array) != 1:
        raise RuntimeError(
            "❌ One-day forecast length is invalid."
        )

    print(
        "✅ One-day forecast length is valid."
    )

    if not np.isfinite(
        one_day_array
    ).all():
        raise RuntimeError(
            "❌ One-day forecast contains invalid values."
        )

    print(
        "✅ One-day prediction is finite."
    )

    if (one_day_array <= 0).any():
        raise RuntimeError(
            "❌ One-day forecast contains "
            "non-positive values."
        )

    print(
        "✅ One-day prediction is positive."
    )

    if len(forecast_array) != FORECAST_STEPS:
        raise RuntimeError(
            "❌ Multi-step forecast length is invalid."
        )

    print(
        f"✅ {FORECAST_STEPS}-day forecast length is valid."
    )

    if not np.isfinite(
        forecast_array
    ).all():
        raise RuntimeError(
            "❌ Multi-step forecast contains "
            "invalid values."
        )

    print(
        f"✅ {FORECAST_STEPS}-day forecast "
        "contains valid values."
    )

    if (forecast_array <= 0).any():
        raise RuntimeError(
            "❌ Multi-step forecast contains "
            "non-positive values."
        )

    print(
        "✅ All forecast prices are positive."
    )

    if movement_signal not in {
        "UP",
        "DOWN",
        "FLAT",
    }:
        raise RuntimeError(
            "❌ Invalid movement signal."
        )

    print(
        "✅ Movement signal is valid."
    )

    # =========================================================================
    # 14. REGISTRY / ARTIFACT CONSISTENCY
    # =========================================================================

    print()
    print("=" * 78)
    print("14. REGISTRY / ARTIFACT CONSISTENCY")
    print("=" * 78)

    registered = await (
        registry_repository.get_by_id(
            active_model.id
        )
    )

    if registered is None:
        raise RuntimeError(
            "❌ Active LSTM ModelVersion "
            "disappeared from registry."
        )

    print(
        "✅ ModelVersion still exists in registry."
    )

    if registered.id != active_model.id:
        raise RuntimeError(
            "❌ Registry ID mismatch."
        )

    print(
        "✅ Registry ID is consistent."
    )

    if registered.family != MODEL_FAMILY:
        raise RuntimeError(
            "❌ Registry family mismatch."
        )

    print(
        "✅ Registry family is consistent."
    )

    if registered.symbol != SYMBOL:
        raise RuntimeError(
            "❌ Registry symbol mismatch."
        )

    print(
        "✅ Registry symbol is consistent."
    )

    if (
        registered.version_tag
        != active_model.version_tag
    ):
        raise RuntimeError(
            "❌ Registry version mismatch."
        )

    print(
        "✅ Registry version is consistent."
    )

    if registered.status != "active":
        raise RuntimeError(
            "❌ Registered LSTM model is not active."
        )

    print(
        "✅ Registered model is active."
    )

    if (
        registered.artifact_location
        != active_model.artifact_location
    ):
        raise RuntimeError(
            "❌ Registry artifact location mismatch."
        )

    print(
        "✅ Registry artifact location is consistent."
    )

    # =========================================================================
    # 15. FINAL PIPELINE
    # =========================================================================

    print()
    print("=" * 78)
    print("15. FINAL LSTM INFERENCE PIPELINE")
    print("=" * 78)

    print()
    print("REAL AAPL MARKET DATA")
    print("        ↓")
    print("MARKET DATA REPOSITORY")
    print("        ↓")
    print("REAL CLOSING PRICE HISTORY")
    print("        ↓")
    print(
        f"{LOOKBACK_WINDOW}-STEP LSTM INPUT WINDOW"
    )
    print("        ↓")
    print("ACTIVE MODEL REGISTRY")
    print("        ↓")
    print("MODEL LOADER")
    print("        ↓")
    print("LSTM .PT ARTIFACT")
    print("        ↓")
    print("FITTED LSTM MODEL")
    print("        ↓")
    print("1-DAY FORECAST")
    print("        ↓")
    print(f"{FORECAST_STEPS}-DAY RECURSIVE FORECAST")
    print("        ↓")
    print("UP / DOWN / FLAT SIGNAL")

    # =========================================================================
    # FINAL RESULT
    # =========================================================================

    print()
    print("=" * 78)
    print("🎉 LSTM REAL INFERENCE E2E TEST PASSED")
    print("=" * 78)

    print()
    print("✅ REAL AAPL MARKET DATA USED")
    print("✅ ACTIVE LSTM MODEL FOUND")
    print("✅ MODEL ARTIFACT EXISTS")
    print("✅ LSTM ARTIFACT LOADED")
    print("✅ LSTM MODEL IS FITTED")
    print(
        f"✅ {LOOKBACK_WINDOW}-STEP INPUT VERIFIED"
    )
    print("✅ ONE-DAY FORECAST GENERATED")
    print(
        f"✅ {FORECAST_STEPS}-DAY FORECAST GENERATED"
    )
    print("✅ FORECAST VALUES VERIFIED")
    print("✅ MOVEMENT SIGNAL VERIFIED")
    print("✅ REGISTRY/ARTIFACT CONSISTENCY VERIFIED")

    print()
    print(
        "🚀 INVEST IQ LSTM IS NOW "
        "TRAINED + REGISTERED + LOADABLE + PREDICTING"
    )

    print("=" * 78)


# ============================================================================
# PYTEST ENTRY POINT
# ============================================================================


def test_lstm_real_inference_end_to_end() -> None:
    """
    Pytest entry point for the real LSTM E2E test.
    """

    asyncio.run(main())