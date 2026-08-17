"""
INVEST IQ - REAL PROPHET INFERENCE E2E TEST

End-to-end verification:

    Real Yahoo Finance OHLCV
            ↓
    MarketDataRepository
            ↓
    Real closing-price history
            ↓
    Active Model Registry
            ↓
    Active Prophet ModelVersion
            ↓
    Prophet .pkl artifact
            ↓
    ProphetModel.load()
            ↓
    Fitted Prophet model
            ↓
    1-day forecast
            ↓
    5-day forecast
            ↓
    7-day forecast
            ↓
    30-day forecast
            ↓
    Uncertainty intervals
            ↓
    UP / DOWN / FLAT signal

No mock market data is used.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)

from src.infrastructure.ml.model_registry.file_system_model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.ml.models.prophet_model import (
    ProphetModel,
)


pytestmark = pytest.mark.slow


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILY = "prophet"

LOOKBACK_DAYS = 400

FORECAST_STEPS = 5

FORECAST_STEPS_7 = 7

FORECAST_STEPS_30 = 30


# ============================================================================
# SERVICE PATHS
# ============================================================================

# Test file:
#
# /app/tests/e2e/test_predict_prophet.py
#
# parents[0] = /app/tests/e2e
# parents[1] = /app/tests
# parents[2] = /app

SERVICE_ROOT = Path(
    __file__
).resolve().parents[2]


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


def get_movement_signal(
    current_price: float,
    predicted_price: float,
) -> str:
    """
    Convert predicted price movement into a simple directional signal.
    """

    if predicted_price > current_price:
        return "UP"

    if predicted_price < current_price:
        return "DOWN"

    return "FLAT"


def validate_forecast(
    forecast,
    expected_steps: int,
    forecast_name: str,
) -> np.ndarray:
    """
    Validate a Prophet forecast and return a float64 numpy array.
    """

    if forecast is None:
        raise RuntimeError(
            f"{forecast_name} returned None."
        )

    forecast_array = np.asarray(
        forecast,
        dtype=np.float64,
    ).reshape(-1)

    if len(forecast_array) != expected_steps:
        raise RuntimeError(
            f"{forecast_name} returned "
            f"{len(forecast_array)} values; "
            f"expected {expected_steps}."
        )

    if not np.isfinite(
        forecast_array
    ).all():
        raise RuntimeError(
            f"{forecast_name} contains "
            "NaN or infinite values."
        )

    if (
        forecast_array <= 0
    ).any():
        raise RuntimeError(
            f"{forecast_name} contains "
            "non-positive prices."
        )

    return forecast_array


# ============================================================================
# MAIN
# ============================================================================


async def main() -> None:

    print()
    print_separator()
    print(
        "INVEST IQ - REAL PROPHET INFERENCE E2E TEST"
    )
    print_separator()

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    print()
    print("CONFIGURATION")
    print("-" * 78)

    print(
        f"SYMBOL              : {SYMBOL}"
    )

    print(
        f"MODEL FAMILY        : {MODEL_FAMILY}"
    )

    print(
        f"LOOKBACK DAYS       : {LOOKBACK_DAYS}"
    )

    print(
        f"FORECAST STEPS      : {FORECAST_STEPS}"
    )

    print(
        f"7-DAY FORECAST      : {FORECAST_STEPS_7}"
    )

    print(
        f"30-DAY FORECAST     : {FORECAST_STEPS_30}"
    )

    print(
        f"SERVICE ROOT        : {SERVICE_ROOT}"
    )

    print(
        f"ARTIFACT ROOT       : {ARTIFACT_ROOT}"
    )

    print(
        f"REGISTRY ROOT       : {REGISTRY_ROOT}"
    )

    # =========================================================================
    # 1. MARKET DATA REPOSITORY
    # =========================================================================

    print()
    print_separator()
    print(
        "1. MARKET DATA REPOSITORY"
    )
    print_separator()

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
    print_separator()
    print(
        "2. MODEL REGISTRY"
    )
    print_separator()

    registry_repository = (
        FileSystemModelRegistryRepository()
    )

    print(
        "✅ FileSystemModelRegistryRepository created."
    )

    # =========================================================================
    # 3. ACTIVE PROPHET MODEL LOOKUP
    # =========================================================================

    print()
    print_separator()
    print(
        "3. ACTIVE PROPHET MODEL LOOKUP"
    )
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
            f"❌ No active Prophet model found "
            f"for {SYMBOL}."
        )

    print(
        "✅ Active Prophet model found."
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
    print_separator()
    print(
        "4. ACTIVE MODEL VALIDATION"
    )
    print_separator()

    if (
        active_model.family
        != MODEL_FAMILY
    ):
        raise RuntimeError(
            "❌ Active model family "
            "does not match Prophet."
        )

    print(
        "✅ Model family verified."
    )

    if (
        active_model.symbol.upper().strip()
        != SYMBOL
    ):
        raise RuntimeError(
            "❌ Active model symbol "
            "does not match AAPL."
        )

    print(
        "✅ Model symbol verified."
    )

    if active_model.status != "active":
        raise RuntimeError(
            "❌ Registered Prophet model "
            "is not active."
        )

    print(
        "✅ Model status verified."
    )

    artifact_path = Path(
        active_model.artifact_location
    )

    if not artifact_path.exists():
        raise RuntimeError(
            "❌ Registered Prophet artifact "
            "does not exist."
        )

    print(
        "✅ Registered artifact exists."
    )

    if not artifact_path.is_file():
        raise RuntimeError(
            "❌ Registered Prophet artifact "
            "is not a file."
        )

    print(
        "✅ Registered artifact is a file."
    )

    artifact_size = (
        artifact_path.stat().st_size
    )

    if artifact_size <= 0:
        raise RuntimeError(
            "❌ Registered Prophet artifact "
            "is empty."
        )

    print(
        f"✅ Artifact size: "
        f"{artifact_size:,} bytes"
    )

    if (
        artifact_path.suffix.lower()
        != ".pkl"
    ):
        raise RuntimeError(
            "❌ Prophet artifact must use "
            "the .pkl extension."
        )

    print(
        "✅ Artifact extension is .pkl."
    )

    # =========================================================================
    # 5. REAL MARKET DATA
    # =========================================================================

    print()
    print_separator()
    print(
        "5. REAL MARKET DATA"
    )
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
            "❌ No real OHLCV data returned."
        )

    print(
        f"✅ Received {len(bars)} "
        "REAL OHLCV bars."
    )

    # =========================================================================
    # 6. REAL CLOSE PRICE SERIES
    # =========================================================================

    print()
    print_separator()
    print(
        "6. REAL CLOSE PRICE SERIES"
    )
    print_separator()

    close_prices = np.asarray(
        [
            float(bar.close)
            for bar in bars
        ],
        dtype=np.float64,
    )

    if len(close_prices) == 0:
        raise RuntimeError(
            "❌ Close-price series is empty."
        )

    if not np.isfinite(
        close_prices
    ).all():
        raise RuntimeError(
            "❌ Close-price series contains "
            "NaN or infinite values."
        )

    if (
        close_prices <= 0
    ).any():
        raise RuntimeError(
            "❌ Close-price series contains "
            "non-positive values."
        )

    current_price = float(
        close_prices[-1]
    )

    latest_date = bars[-1].bar_time

    print(
        f"Total close prices   : "
        f"{len(close_prices)}"
    )

    print(
        f"Latest trading date  : "
        f"{latest_date}"
    )

    print(
        f"Latest close         : "
        f"{current_price:.4f}"
    )

    print()
    print(
        "LATEST 10 CLOSE PRICES"
    )

    latest_count = min(
        10,
        len(close_prices),
    )

    for index, price in enumerate(
        close_prices[-latest_count:],
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{price:.6f}"
        )

    # =========================================================================
    # 7. LOAD ACTIVE PROPHET MODEL
    # =========================================================================

    print()
    print_separator()
    print(
        "7. LOAD ACTIVE PROPHET MODEL"
    )
    print_separator()

    print(
        "📦 Loading active Prophet artifact..."
    )

    model = ProphetModel.load(
        artifact_path
    )

    if model is None:
        raise RuntimeError(
            "❌ ProphetModel.load() returned None."
        )

    print(
        "✅ Prophet artifact loaded."
    )

    print(
        f"Loaded model type: "
        f"{type(model).__name__}"
    )

    if not isinstance(
        model,
        ProphetModel,
    ):
        raise RuntimeError(
            "❌ Loaded model is not "
            "a ProphetModel instance."
        )

    print(
        "✅ Loaded model is a ProphetModel."
    )

    # =========================================================================
    # 8. MODEL FIT VALIDATION
    # =========================================================================

    print()
    print_separator()
    print(
        "8. PROPHET MODEL VALIDATION"
    )
    print_separator()

    if hasattr(
        model,
        "is_fitted",
    ):
        if not model.is_fitted:
            raise RuntimeError(
                "❌ Loaded Prophet model "
                "is not fitted."
            )

        print(
            "✅ Prophet model is fitted."
        )

    else:
        print(
            "ℹ️ ProphetModel does not expose "
            "an is_fitted property; "
            "artifact load succeeded."
        )

    # =========================================================================
    # 9. ONE-DAY FORECAST
    # =========================================================================

    print()
    print_separator()
    print(
        "9. ONE-DAY PROPHET FORECAST"
    )
    print_separator()

    print(
        "🧠 Running one-step Prophet inference..."
    )

    one_day_forecast = (
        model.predict_next(
            steps_ahead=1
        )
    )

    one_day_array = validate_forecast(
        one_day_forecast,
        expected_steps=1,
        forecast_name="One-day Prophet forecast",
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

    signal = get_movement_signal(
        current_price,
        next_price,
    )

    print()
    print(
        "LATEST MARKET INFORMATION"
    )

    print(
        f"Trading date       : "
        f"{latest_date}"
    )

    print(
        f"Latest close       : "
        f"{current_price:.4f}"
    )

    print()
    print(
        "PROPHET OUTPUT"
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
        f"{signal}"
    )

    # =========================================================================
    # 10. FIVE-DAY FORECAST
    # =========================================================================

    print()
    print_separator()
    print(
        "10. 5-DAY PROPHET FORECAST"
    )
    print_separator()

    print(
        f"🧠 Generating {FORECAST_STEPS}-step "
        "Prophet forecast..."
    )

    forecast_5 = model.predict_next(
        steps_ahead=FORECAST_STEPS
    )

    forecast_5_array = validate_forecast(
        forecast_5,
        expected_steps=FORECAST_STEPS,
        forecast_name="5-day Prophet forecast",
    )

    print()

    previous_price = current_price

    for index, prediction in enumerate(
        forecast_5_array,
        start=1,
    ):
        prediction = float(
            prediction
        )

        change_from_current = (
            prediction
            - current_price
        )

        change_from_current_percent = (
            change_from_current
            / current_price
            * 100.0
        )

        step_change = (
            prediction
            - previous_price
        )

        print(
            f"Day +{index}: "
            f"{prediction:.4f} | "
            f"change from current: "
            f"{change_from_current:+.4f} "
            f"({change_from_current_percent:+.2f}%) | "
            f"step change: "
            f"{step_change:+.4f}"
        )

        previous_price = prediction

    # =========================================================================
    # 11. SEVEN-DAY FORECAST
    # =========================================================================

    print()
    print_separator()
    print(
        "11. 7-DAY PROPHET FORECAST"
    )
    print_separator()

    print(
        "🧠 Generating 7-step Prophet forecast..."
    )

    forecast_7 = model.predict_next(
        steps_ahead=FORECAST_STEPS_7
    )

    forecast_7_array = validate_forecast(
        forecast_7,
        expected_steps=FORECAST_STEPS_7,
        forecast_name="7-day Prophet forecast",
    )

    print()

    for index, prediction in enumerate(
        forecast_7_array,
        start=1,
    ):
        prediction = float(
            prediction
        )

        print(
            f"Day +{index}: "
            f"{prediction:.4f}"
        )

    # =========================================================================
    # 12. THIRTY-DAY FORECAST
    # =========================================================================

    print()
    print_separator()
    print(
        "12. 30-DAY PROPHET FORECAST"
    )
    print_separator()

    print(
        "🧠 Generating 30-step Prophet forecast..."
    )

    forecast_30 = model.predict_next(
        steps_ahead=FORECAST_STEPS_30
    )

    forecast_30_array = validate_forecast(
        forecast_30,
        expected_steps=FORECAST_STEPS_30,
        forecast_name="30-day Prophet forecast",
    )

    print()
    print(
        "30-day forecast generated successfully."
    )

    print(
        f"Day +1  : "
        f"{forecast_30_array[0]:.4f}"
    )

    print(
        f"Day +7  : "
        f"{forecast_30_array[6]:.4f}"
    )

    print(
        f"Day +14 : "
        f"{forecast_30_array[13]:.4f}"
    )

    print(
        f"Day +21 : "
        f"{forecast_30_array[20]:.4f}"
    )

    print(
        f"Day +30 : "
        f"{forecast_30_array[29]:.4f}"
    )

    # =========================================================================
    # 13. UNCERTAINTY INTERVALS
    # =========================================================================

    print()
    print_separator()
    print(
        "13. PROPHET UNCERTAINTY INTERVALS"
    )
    print_separator()

    print(
        "🧠 Generating Prophet uncertainty intervals..."
    )

    intervals = (
        model.predict_next_with_intervals(
            steps_ahead=FORECAST_STEPS
        )
    )

    if intervals is None:
        raise RuntimeError(
            "❌ Prophet interval forecast returned None."
        )

    if len(intervals) != FORECAST_STEPS:
        raise RuntimeError(
            "❌ Prophet interval forecast returned "
            f"{len(intervals)} values; "
            f"expected {FORECAST_STEPS}."
        )

    print()

    for index, interval in enumerate(
        intervals,
        start=1,
    ):

        if len(interval) != 3:
            raise RuntimeError(
                f"❌ Invalid uncertainty interval "
                f"structure at day +{index}."
            )

        predicted = float(
            interval[0]
        )

        lower = float(
            interval[1]
        )

        upper = float(
            interval[2]
        )

        interval_values = np.asarray(
            [
                predicted,
                lower,
                upper,
            ],
            dtype=np.float64,
        )

        if not np.isfinite(
            interval_values
        ).all():
            raise RuntimeError(
                f"❌ Invalid uncertainty interval "
                f"at day +{index}."
            )

        if predicted <= 0:
            raise RuntimeError(
                f"❌ Prediction is non-positive "
                f"at day +{index}."
            )

        if lower <= 0:
            raise RuntimeError(
                f"❌ Lower interval bound is "
                f"non-positive at day +{index}."
            )

        if upper <= 0:
            raise RuntimeError(
                f"❌ Upper interval bound is "
                f"non-positive at day +{index}."
            )

        if lower > predicted:
            raise RuntimeError(
                f"❌ Lower bound is above prediction "
                f"at day +{index}."
            )

        if upper < predicted:
            raise RuntimeError(
                f"❌ Upper bound is below prediction "
                f"at day +{index}."
            )

        if lower > upper:
            raise RuntimeError(
                f"❌ Lower bound is above upper bound "
                f"at day +{index}."
            )

        print(
            f"Day +{index}: "
            f"prediction={predicted:.4f} | "
            f"lower={lower:.4f} | "
            f"upper={upper:.4f}"
        )

    print(
        "✅ Prophet uncertainty intervals are valid."
    )

    # =========================================================================
    # 14. FORECAST VALIDATION
    # =========================================================================

    print()
    print_separator()
    print(
        "14. FORECAST VALIDATION"
    )
    print_separator()

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
            "❌ One-day forecast contains "
            "invalid values."
        )

    print(
        "✅ One-day prediction is finite."
    )

    if (
        one_day_array <= 0
    ).any():
        raise RuntimeError(
            "❌ One-day forecast contains "
            "non-positive values."
        )

    print(
        "✅ One-day prediction is positive."
    )

    if len(forecast_5_array) != 5:
        raise RuntimeError(
            "❌ 5-day forecast length is invalid."
        )

    print(
        "✅ 5-day forecast length is valid."
    )

    if len(forecast_7_array) != 7:
        raise RuntimeError(
            "❌ 7-day forecast length is invalid."
        )

    print(
        "✅ 7-day forecast length is valid."
    )

    if len(forecast_30_array) != 30:
        raise RuntimeError(
            "❌ 30-day forecast length is invalid."
        )

    print(
        "✅ 30-day forecast length is valid."
    )

    if not np.isfinite(
        forecast_5_array
    ).all():
        raise RuntimeError(
            "❌ 5-day forecast contains "
            "invalid values."
        )

    if not np.isfinite(
        forecast_7_array
    ).all():
        raise RuntimeError(
            "❌ 7-day forecast contains "
            "invalid values."
        )

    if not np.isfinite(
        forecast_30_array
    ).all():
        raise RuntimeError(
            "❌ 30-day forecast contains "
            "invalid values."
        )

    print(
        "✅ All forecast values are finite."
    )

    if (
        forecast_5_array <= 0
    ).any():
        raise RuntimeError(
            "❌ 5-day forecast contains "
            "non-positive values."
        )

    if (
        forecast_7_array <= 0
    ).any():
        raise RuntimeError(
            "❌ 7-day forecast contains "
            "non-positive values."
        )

    if (
        forecast_30_array <= 0
    ).any():
        raise RuntimeError(
            "❌ 30-day forecast contains "
            "non-positive values."
        )

    print(
        "✅ All forecast prices are positive."
    )

    if signal not in {
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
    # 15. REGISTRY / ARTIFACT CONSISTENCY
    # =========================================================================

    print()
    print_separator()
    print(
        "15. REGISTRY / ARTIFACT CONSISTENCY"
    )
    print_separator()

    registered_model = await (
        registry_repository.get_by_id(
            active_model.id
        )
    )

    if registered_model is None:
        raise RuntimeError(
            "❌ Active Prophet ModelVersion "
            "could not be loaded by ID."
        )

    print(
        "✅ ModelVersion still exists in registry."
    )

    if (
        registered_model.id
        != active_model.id
    ):
        raise RuntimeError(
            "❌ Registry ID mismatch."
        )

    print(
        "✅ Registry ID is consistent."
    )

    if (
        registered_model.family
        != MODEL_FAMILY
    ):
        raise RuntimeError(
            "❌ Registry family mismatch."
        )

    print(
        "✅ Registry family is consistent."
    )

    if (
        registered_model.symbol
        != SYMBOL
    ):
        raise RuntimeError(
            "❌ Registry symbol mismatch."
        )

    print(
        "✅ Registry symbol is consistent."
    )

    if (
        registered_model.status
        != "active"
    ):
        raise RuntimeError(
            "❌ Registered Prophet model "
            "is no longer active."
        )

    print(
        "✅ Registered model is active."
    )

    if (
        registered_model.version_tag
        != active_model.version_tag
    ):
        raise RuntimeError(
            "❌ Registry version mismatch."
        )

    print(
        "✅ Registry version is consistent."
    )

    if (
        registered_model.artifact_location
        != active_model.artifact_location
    ):
        raise RuntimeError(
            "❌ Registry artifact location mismatch."
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
    # 16. FINAL PIPELINE
    # =========================================================================

    print()
    print_separator()
    print(
        "16. FINAL PROPHET INFERENCE PIPELINE"
    )
    print_separator()

    print()
    print(
        "REAL AAPL MARKET DATA"
    )

    print(
        "        ↓"
    )

    print(
        "MARKET DATA REPOSITORY"
    )

    print(
        "        ↓"
    )

    print(
        "REAL CLOSING PRICE HISTORY"
    )

    print(
        "        ↓"
    )

    print(
        "ACTIVE PROPHET MODEL REGISTRY"
    )

    print(
        "        ↓"
    )

    print(
        "PROPHET .PKL ARTIFACT"
    )

    print(
        "        ↓"
    )

    print(
        "FITTED PROPHET MODEL"
    )

    print(
        "        ↓"
    )

    print(
        "1-DAY FORECAST"
    )

    print(
        "        ↓"
    )

    print(
        "5-DAY FORECAST"
    )

    print(
        "        ↓"
    )

    print(
        "7-DAY FORECAST"
    )

    print(
        "        ↓"
    )

    print(
        "30-DAY FORECAST"
    )

    print(
        "        ↓"
    )

    print(
        "UNCERTAINTY INTERVALS"
    )

    print(
        "        ↓"
    )

    print(
        "UP / DOWN / FLAT SIGNAL"
    )

    # =========================================================================
    # FINAL RESULT
    # =========================================================================

    print()
    print_separator()
    print(
        "🎉 PROPHET REAL INFERENCE E2E TEST PASSED"
    )
    print_separator()

    print()
    print(
        "✅ REAL AAPL MARKET DATA USED"
    )

    print(
        "✅ ACTIVE PROPHET MODEL FOUND"
    )

    print(
        "✅ MODEL ARTIFACT EXISTS"
    )

    print(
        "✅ PROPHET ARTIFACT LOADED"
    )

    print(
        "✅ PROPHET MODEL VALIDATED"
    )

    print(
        "✅ REAL CLOSING PRICE HISTORY USED"
    )

    print(
        "✅ ONE-DAY FORECAST GENERATED"
    )

    print(
        "✅ 5-DAY FORECAST GENERATED"
    )

    print(
        "✅ 7-DAY FORECAST GENERATED"
    )

    print(
        "✅ 30-DAY FORECAST GENERATED"
    )

    print(
        "✅ UNCERTAINTY INTERVALS GENERATED"
    )

    print(
        "✅ FORECAST VALUES VERIFIED"
    )

    print(
        "✅ MOVEMENT SIGNAL VERIFIED"
    )

    print(
        "✅ REGISTRY / ARTIFACT CONSISTENCY VERIFIED"
    )

    print()
    print(
        "🚀 INVEST IQ PROPHET IS NOW "
        "TRAINED + REGISTERED + LOADABLE + PREDICTING"
    )

    print_separator()


# ============================================================================
# PYTEST ENTRY POINT
# ============================================================================


def test_prophet_real_inference_end_to_end() -> None:
    """
    Pytest entry point for the real Prophet E2E test.
    """

    asyncio.run(main())