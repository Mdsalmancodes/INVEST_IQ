"""
INVEST IQ - REAL ARIMA INFERENCE E2E TEST

End-to-end verification:

    Active Model Registry
            ↓
    ARIMA ModelVersion
            ↓
    ARIMA .pkl artifact
            ↓
    ModelLoader
            ↓
    ArimaModel
            ↓
    Real AAPL market data
            ↓
    Active fitted ARIMA model
            ↓
    1-day forecast
            ↓
    5-day forecast
            ↓
    UP / DOWN / FLAT movement signal

No mock market data is used.
"""

from __future__ import annotations

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

from src.infrastructure.ml.models.arima_model import (
    ArimaModel,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILY = "arima"

LOOKBACK_DAYS = 400

MIN_HISTORY_BARS = 30

FORECAST_STEPS = 5


# ============================================================================
# SERVICE ROOT
# ============================================================================
#
# File location:
#
# apps/
#   ai-service/
#       tests/
#           e2e/
#               test_predict_arima.py
#
# parents[0] = e2e
# parents[1] = tests
# parents[2] = ai-service
#
# Therefore this works both:
#
# Host:
# C:\...\INVEST_IQ\apps\ai-service
#
# Docker:
# /app
#
# ============================================================================

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
        df["bar_time"]
    )

    df = df.sort_values(
        "bar_time"
    )

    if df["bar_time"].duplicated().any():
        raise RuntimeError(
            "OHLCV dataframe contains duplicate timestamps."
        )

    df = df.set_index(
        "bar_time"
    )

    return df


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

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"OHLCV dataframe is missing columns: {missing}"
        )

    if df.empty:
        raise RuntimeError(
            "OHLCV dataframe is empty."
        )

    if df.index.has_duplicates:
        raise RuntimeError(
            "OHLCV dataframe contains duplicate timestamps."
        )

    if not df.index.is_monotonic_increasing:
        raise RuntimeError(
            "OHLCV timestamps are not chronologically ordered."
        )

    if df[required_columns].isna().any().any():
        raise RuntimeError(
            "OHLCV dataframe contains NaN values."
        )

    numeric_values = df[
        required_columns
    ].to_numpy(
        dtype=float
    )

    if not np.isfinite(
        numeric_values
    ).all():
        raise RuntimeError(
            "OHLCV dataframe contains NaN "
            "or infinite numeric values."
        )

    if (
        df["close"] <= 0
    ).any():
        raise RuntimeError(
            "OHLCV close prices must be positive."
        )

    if (
        df["volume"] < 0
    ).any():
        raise RuntimeError(
            "OHLCV volume cannot be negative."
        )


def validate_forecast(
    forecast,
    expected_steps: int,
    name: str,
) -> np.ndarray:
    """
    Validate an ARIMA forecast and return it as float64 numpy array.
    """

    if forecast is None:
        raise RuntimeError(
            f"{name} returned None."
        )

    forecast_array = np.asarray(
        forecast,
        dtype=np.float64,
    )

    if forecast_array.ndim != 1:
        raise RuntimeError(
            f"{name} must return a one-dimensional forecast."
        )

    if len(forecast_array) != expected_steps:
        raise RuntimeError(
            f"{name} returned {len(forecast_array)} values; "
            f"expected {expected_steps}."
        )

    if not np.isfinite(
        forecast_array
    ).all():
        raise RuntimeError(
            f"{name} contains NaN or infinite values."
        )

    if (
        forecast_array <= 0
    ).any():
        raise RuntimeError(
            f"{name} contains non-positive forecast prices."
        )

    return forecast_array


# ============================================================================
# REAL ARIMA INFERENCE E2E TEST
# ============================================================================


@pytest.mark.slow
async def test_arima_real_inference_end_to_end() -> None:
    """
    Verify real ARIMA inference from active registry model
    through real market data and multi-step forecasting.
    """

    print()
    print("=" * 78)
    print("INVEST IQ - REAL ARIMA INFERENCE E2E TEST")
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
    # 3. ACTIVE ARIMA MODEL LOOKUP
    # =========================================================================

    print()
    print("=" * 78)
    print("3. ACTIVE ARIMA MODEL LOOKUP")
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
            f"No active {MODEL_FAMILY} model found for {SYMBOL}."
        )

    print(
        "✅ Active ARIMA model found."
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

    assert active_model.family == MODEL_FAMILY, (
        "Active model family is not ARIMA."
    )

    print(
        "✅ Model family verified."
    )

    assert active_model.symbol == SYMBOL, (
        "Active model symbol is not AAPL."
    )

    print(
        "✅ Model symbol verified."
    )

    assert active_model.status == "active", (
        "ARIMA model is not active."
    )

    print(
        "✅ Model status verified."
    )

    artifact_path = Path(
        active_model.artifact_location
    )

    assert artifact_path.exists(), (
        "Registered ARIMA artifact does not exist."
    )

    print(
        "✅ Registered artifact exists."
    )

    assert artifact_path.is_file(), (
        "Registered ARIMA artifact is not a file."
    )

    print(
        "✅ Registered artifact is a file."
    )

    artifact_size = (
        artifact_path.stat().st_size
    )

    assert artifact_size > 0, (
        "ARIMA artifact is empty."
    )

    print(
        f"✅ Artifact size: "
        f"{artifact_size:,} bytes"
    )

    assert artifact_path.suffix.lower() == ".pkl", (
        "ARIMA artifact must use .pkl extension."
    )

    print(
        "✅ Artifact extension is .pkl."
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

    print(
        f"✅ Received {len(bars)} real OHLCV bars."
    )

    assert len(bars) >= MIN_HISTORY_BARS, (
        "Not enough real OHLCV history for ARIMA inference."
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

    latest_row = df.iloc[-1]

    print()
    print(
        "LATEST OHLCV BAR"
    )

    print(
        latest_row[
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ].to_string()
    )

    # =========================================================================
    # 7. REAL CLOSE PRICE SERIES
    # =========================================================================

    print()
    print("=" * 78)
    print("7. REAL CLOSE PRICE SERIES")
    print("=" * 78)

    close_prices = df[
        "close"
    ].to_numpy(
        dtype=np.float64
    )

    assert len(close_prices) >= MIN_HISTORY_BARS, (
        "ARIMA requires sufficient close-price history."
    )

    assert np.isfinite(
        close_prices
    ).all(), (
        "Close price series contains NaN or infinite values."
    )

    assert (
        close_prices > 0
    ).all(), (
        "Close price series contains non-positive values."
    )

    print(
        f"Total close prices : "
        f"{len(close_prices)}"
    )

    current_price = float(
        close_prices[-1]
    )

    print(
        f"Latest close       : "
        f"{current_price:.4f}"
    )

    print()
    print(
        "LATEST 10 CLOSE PRICES"
    )

    for index, price in enumerate(
        close_prices[-10:],
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
        artifact_root=(
            ARTIFACT_ROOT
        ),
    )

    print(
        "✅ ModelLoader created."
    )

    # =========================================================================
    # 9. LOAD ACTIVE ARIMA
    # =========================================================================

    print()
    print("=" * 78)
    print("9. LOAD ACTIVE ARIMA")
    print("=" * 78)

    print(
        "📦 Loading active ARIMA artifact..."
    )

    model = await model_loader.load_model(
        family=MODEL_FAMILY,
        symbol=SYMBOL,
    )

    assert model is not None, (
        "ModelLoader returned None for active ARIMA."
    )

    print(
        "✅ ARIMA artifact loaded."
    )

    print(
        f"Loaded model type: "
        f"{type(model).__name__}"
    )

    # =========================================================================
    # 10. ARIMA MODEL VALIDATION
    # =========================================================================

    print()
    print("=" * 78)
    print("10. ARIMA MODEL VALIDATION")
    print("=" * 78)

    assert isinstance(
        model,
        ArimaModel,
    ), (
        "Loaded model is not an ArimaModel instance."
    )

    print(
        "✅ Loaded model is an ArimaModel."
    )

    assert model.is_fitted, (
        "Loaded ARIMA model is not fitted."
    )

    print(
        "✅ ARIMA model is fitted."
    )

    print(
        f"ARIMA order: "
        f"{model.order}"
    )

    assert model.has_sufficient_history(
        len(close_prices)
    ), (
        "Real close-price history does not satisfy "
        "ARIMA minimum history requirement."
    )

    print(
        "✅ ARIMA history requirement is valid."
    )

    # =========================================================================
    # 11. ONE-DAY ARIMA FORECAST
    # =========================================================================

    print()
    print("=" * 78)
    print("11. ONE-DAY ARIMA FORECAST")
    print("=" * 78)

    print(
        "🧠 Running one-step ARIMA inference..."
    )

    one_day_forecast = (
        model.predict_next(
            steps_ahead=1
        )
    )

    one_day_array = validate_forecast(
        one_day_forecast,
        expected_steps=1,
        name="ARIMA one-day forecast",
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
        "ARIMA OUTPUT"
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
    # 12. MULTI-STEP ARIMA FORECAST
    # =========================================================================

    print()
    print("=" * 78)
    print(
        f"12. {FORECAST_STEPS}-STEP ARIMA FORECAST"
    )
    print("=" * 78)

    print(
        f"🧠 Generating {FORECAST_STEPS}-step ARIMA forecast..."
    )

    forecast = model.predict_next(
        steps_ahead=FORECAST_STEPS
    )

    forecast_array = validate_forecast(
        forecast,
        expected_steps=FORECAST_STEPS,
        name=f"ARIMA {FORECAST_STEPS}-step forecast",
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

    assert len(one_day_array) == 1

    print(
        "✅ One-day forecast length is valid."
    )

    assert np.isfinite(
        one_day_array
    ).all()

    print(
        "✅ One-day prediction is finite."
    )

    assert (
        one_day_array > 0
    ).all()

    print(
        "✅ One-day prediction is positive."
    )

    assert len(forecast_array) == FORECAST_STEPS

    print(
        f"✅ {FORECAST_STEPS}-day forecast length is valid."
    )

    assert np.isfinite(
        forecast_array
    ).all()

    print(
        f"✅ {FORECAST_STEPS}-day forecast contains valid values."
    )

    assert (
        forecast_array > 0
    ).all()

    print(
        "✅ All forecast prices are positive."
    )

    assert movement_signal in {
        "UP",
        "DOWN",
        "FLAT",
    }

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

    assert registered is not None, (
        "Active ARIMA ModelVersion disappeared from registry."
    )

    print(
        "✅ ModelVersion still exists in registry."
    )

    assert registered.id == active_model.id, (
        "Registry ID mismatch."
    )

    print(
        "✅ Registry ID is consistent."
    )

    assert (
        registered.family
        == active_model.family
    ), (
        "Registry family mismatch."
    )

    print(
        "✅ Registry family is consistent."
    )

    assert (
        registered.symbol
        == active_model.symbol
    ), (
        "Registry symbol mismatch."
    )

    print(
        "✅ Registry symbol is consistent."
    )

    assert (
        registered.version_tag
        == active_model.version_tag
    ), (
        "Registry version mismatch."
    )

    print(
        "✅ Registry version is consistent."
    )

    assert (
        registered.artifact_location
        == active_model.artifact_location
    ), (
        "Registry artifact location mismatch."
    )

    print(
        "✅ Registry artifact location is consistent."
    )

    print(
        f"Version : "
        f"{active_model.version_tag}"
    )

    print(
        f"Artifact: "
        f"{active_model.artifact_location}"
    )

    # =========================================================================
    # 15. FINAL PIPELINE
    # =========================================================================

    print()
    print("=" * 78)
    print("15. FINAL ARIMA INFERENCE PIPELINE")
    print("=" * 78)

    print()
    print("REAL AAPL MARKET DATA")
    print("        ↓")
    print("REAL CLOSING PRICE HISTORY")
    print("        ↓")
    print("ACTIVE ARIMA MODEL REGISTRY")
    print("        ↓")
    print("MODEL LOADER")
    print("        ↓")
    print("ARIMA .PKL ARTIFACT")
    print("        ↓")
    print("FITTED ARIMA MODEL")
    print("        ↓")
    print("1-DAY FORECAST")
    print("        ↓")
    print("5-DAY FORECAST")
    print("        ↓")
    print("UP / DOWN / FLAT MOVEMENT SIGNAL")

    # =========================================================================
    # FINAL RESULT
    # =========================================================================

    print()
    print("=" * 78)
    print("🎉 ARIMA REAL INFERENCE E2E TEST PASSED")
    print("=" * 78)

    print()
    print("✅ REAL AAPL MARKET DATA USED")
    print("✅ ACTIVE ARIMA MODEL FOUND")
    print("✅ MODEL ARTIFACT EXISTS")
    print("✅ ARIMA ARTIFACT LOADED")
    print("✅ ARIMA MODEL IS FITTED")
    print("✅ REAL CLOSING PRICE HISTORY VALIDATED")
    print("✅ ONE-DAY FORECAST GENERATED")
    print(
        f"✅ {FORECAST_STEPS}-DAY FORECAST GENERATED"
    )
    print("✅ FORECAST VALUES VERIFIED")
    print("✅ MOVEMENT SIGNAL VERIFIED")
    print("✅ REGISTRY/ARTIFACT CONSISTENCY VERIFIED")

    print()
    print(
        "🚀 INVEST IQ ARIMA IS NOW "
        "TRAINED + REGISTERED + LOADABLE + PREDICTING"
    )

    print("=" * 78)