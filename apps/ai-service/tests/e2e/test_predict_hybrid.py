
"""
INVEST IQ - REAL SIX-MODEL HYBRID PREDICTION E2E TEST

Verifies the complete production prediction pipeline:

    Real AAPL market data
            ↓
    MarketDataRepository
            ↓
    PredictUseCase
            ↓
    ModelLoader
            ↓
    LSTM
    ARIMA
    Prophet
    Random Forest
    XGBoost
    FinBERT
            ↓
    DecisionEngine
            ↓
    Weighted hybrid ensemble
            ↓
    BUY / HOLD / SELL
            ↓
    1d / 7d / 30d forecasts
            ↓
    PredictionRun persistence

No mocked models are used.
No synthetic market data is used.
No training is performed during prediction.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.application.ml.decision_engine import DecisionEngine
from src.application.ml.predict_use_case import PredictUseCase

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)

from src.infrastructure.ml.model_registry.model_loader import (
    ModelLoader,
)

from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.persistence.prediction_run_repository import (
    FileSystemPredictionRunRepository,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

LOOKBACK_DAYS = 400

NEWS_TEXTS = [
    "Apple reported strong quarterly earnings and revenue growth.",
    "The company continues to show strong demand for its products.",
    "Apple announced positive quarterly financial results.",
]


# ============================================================================
# PATHS
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

PREDICTION_RUN_ROOT = (
    SERVICE_ROOT
    / "data"
    / "prediction_runs"
)


# ============================================================================
# VALIDATION HELPERS
# ============================================================================


def validate_prediction_result(result) -> None:
    """
    Validate the complete DecisionEngineResult.
    """

    assert result is not None

    # ------------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------------

    recommendation = result.recommendation

    assert recommendation is not None

    assert recommendation.symbol == SYMBOL

    assert recommendation.verdict in {
        "buy",
        "hold",
        "sell",
    }

    confidence = recommendation.confidence

    confidence_value = (
        confidence.value
        if hasattr(confidence, "value")
        else confidence
    )

    assert np.isfinite(float(confidence_value))

    assert 0.0 <= float(confidence_value) <= 1.0

    # ------------------------------------------------------------------------
    # Forecasts
    # ------------------------------------------------------------------------

    assert np.isfinite(
        result.price_forecast_1d
    )

    assert np.isfinite(
        result.price_forecast_7d
    )

    assert np.isfinite(
        result.price_forecast_30d
    )

    assert result.price_forecast_1d > 0.0

    assert result.price_forecast_7d > 0.0

    assert result.price_forecast_30d > 0.0

    # ------------------------------------------------------------------------
    # Member signals
    # ------------------------------------------------------------------------

    assert result.member_signals

    for signal in result.member_signals:

        assert signal.model_family in {
            "lstm",
            "arima",
            "prophet",
            "random_forest",
            "xgboost",
            "finbert",
        }

        assert -1.0 <= signal.signal <= 1.0

        assert 0.0 <= signal.confidence <= 1.0

        assert signal.weight >= 0.0

    # ------------------------------------------------------------------------
    # Forecast entities
    # ------------------------------------------------------------------------

    assert result.member_forecasts

    for forecast in result.member_forecasts:

        assert forecast.symbol == SYMBOL

        assert forecast.model_family in {
            "lstm",
            "arima",
            "prophet",
        }

        assert len(forecast.points) == 3

        horizons = {
            point.horizon_days
            for point in forecast.points
        }

        assert horizons == {
            1,
            7,
            30,
        }

        for point in forecast.points:

            assert np.isfinite(
                point.predicted_price
            )

            assert np.isfinite(
                point.lower_bound
            )

            assert np.isfinite(
                point.upper_bound
            )

            assert point.predicted_price > 0.0

            assert (
                point.lower_bound
                <= point.predicted_price
            )

            assert (
                point.upper_bound
                >= point.predicted_price
            )

    # ------------------------------------------------------------------------
    # Explainability
    # ------------------------------------------------------------------------

    assert recommendation.explainability is not None

    assert recommendation.explainability.reasoning

    assert (
        recommendation.verdict
        in recommendation.explainability.reasoning
    )


# ============================================================================
# MODEL LOADER TEST
# ============================================================================


@pytest.mark.slow
async def test_aapl_all_six_models_are_loaded() -> None:
    """
    Verify that ModelLoader loads all six required model families
    for AAPL.
    """

    print()
    print("=" * 78)
    print("INVEST IQ - AAPL SIX-MODEL LOADING TEST")
    print("=" * 78)

    registry = FileSystemModelRegistryRepository(
        REGISTRY_ROOT
    )

    loader = ModelLoader(
        model_registry_repository=registry,
        artifact_root=ARTIFACT_ROOT,
    )

    models = await loader.load_all_models(
        SYMBOL
    )

    assert isinstance(
        models,
        dict,
    )

    required_families = {
        "lstm",
        "arima",
        "prophet",
        "random_forest",
        "xgboost",
        "finbert",
    }

    assert set(models.keys()) == required_families

    print()
    print("MODEL AVAILABILITY:")

    for family in sorted(required_families):

        model = models[family]

        print(
            f"{family:15s} -> "
            f"{'LOADED' if model is not None else 'MISSING'}"
        )

        assert model is not None, (
            f"{family} was not loaded for {SYMBOL}"
        )

    print()
    print("ALL SIX MODELS LOADED SUCCESSFULLY")
    print("=" * 78)


# ============================================================================
# COMPLETE HYBRID PREDICTION TEST
# ============================================================================


@pytest.mark.slow
async def test_aapl_real_six_model_hybrid_prediction_end_to_end() -> None:
    """
    Verify the complete real six-model prediction pipeline.
    """

    print()
    print("=" * 78)
    print("INVEST IQ - REAL SIX-MODEL HYBRID E2E TEST")
    print("=" * 78)

    # ------------------------------------------------------------------------
    # REPOSITORIES
    # ------------------------------------------------------------------------

    market_data_repository = MarketDataRepository()

    registry_repository = (
        FileSystemModelRegistryRepository(
            REGISTRY_ROOT
        )
    )

    model_loader = ModelLoader(
        model_registry_repository=registry_repository,
        artifact_root=ARTIFACT_ROOT,
    )

    prediction_run_repository = (
        FileSystemPredictionRunRepository(
            PREDICTION_RUN_ROOT
        )
    )

    # ------------------------------------------------------------------------
    # DECISION ENGINE
    # ------------------------------------------------------------------------

    decision_engine = DecisionEngine()

    # ------------------------------------------------------------------------
    # PREDICT USE CASE
    # ------------------------------------------------------------------------

    use_case = PredictUseCase(
        market_data_repository=market_data_repository,
        prediction_run_repository=prediction_run_repository,
        decision_engine=decision_engine,
        model_loader=model_loader,
    )

    # ------------------------------------------------------------------------
    # EXECUTE REAL PREDICTION
    # ------------------------------------------------------------------------

    print()
    print("1. REQUEST")
    print(f"   Symbol: {SYMBOL}")
    print(f"   Lookback: {LOOKBACK_DAYS} days")
    print(f"   News items: {len(NEWS_TEXTS)}")

    print()
    print("2. EXECUTING COMPLETE PIPELINE")
    print()

    result = await use_case.execute(
        symbol=SYMBOL,
        news_texts=NEWS_TEXTS,
        lookback_days=LOOKBACK_DAYS,
    )

    print()
    print("3. PIPELINE COMPLETED")

    # ------------------------------------------------------------------------
    # VALIDATE RESULT
    # ------------------------------------------------------------------------

    validate_prediction_result(
        result
    )

    # ------------------------------------------------------------------------
    # ACTIVE MODELS
    # ------------------------------------------------------------------------

    active_models = {
        signal.model_family
        for signal in result.member_signals
    }

    expected_models = {
        "lstm",
        "arima",
        "prophet",
        "random_forest",
        "xgboost",
        "finbert",
    }

    print()
    print("4. ACTIVE MODELS")

    for family in sorted(active_models):

        print(
            f"   {family}"
        )

    assert active_models == expected_models

    # ------------------------------------------------------------------------
    # EXCLUDED MODELS
    # ------------------------------------------------------------------------

    print()
    print("5. EXCLUDED MODELS")

    print(
        f"   {list(result.excluded_models)}"
    )

    assert result.excluded_models == ()

    # ------------------------------------------------------------------------
    # MEMBER SIGNALS
    # ------------------------------------------------------------------------

    print()
    print("6. MODEL SIGNALS")

    for signal in result.member_signals:

        print(
            f"   {signal.model_family:15s} "
            f"signal={signal.signal:+.4f} "
            f"confidence={signal.confidence:.4f} "
            f"weight={signal.weight:.4f}"
        )

    # ------------------------------------------------------------------------
    # WEIGHT VALIDATION
    # ------------------------------------------------------------------------

    total_weight = sum(
        signal.weight
        for signal in result.member_signals
    )

    assert total_weight == pytest.approx(
        1.0,
        abs=1e-6,
    )

    print()
    print(
        f"7. NORMALIZED MODEL WEIGHT = {total_weight:.6f}"
    )

    # ------------------------------------------------------------------------
    # RECOMMENDATION
    # ------------------------------------------------------------------------

    recommendation = result.recommendation

    confidence = recommendation.confidence

    confidence_value = (
        confidence.value
        if hasattr(confidence, "value")
        else confidence
    )

    print()
    print("8. FINAL RECOMMENDATION")

    print(
        f"   Verdict: {recommendation.verdict}"
    )

    print(
        f"   Confidence: {float(confidence_value):.4f}"
    )

    print(
        f"   Sentiment: "
        f"{recommendation.sentiment_score:.4f}"
    )

    print(
        f"   Data quality: "
        f"{recommendation.data_quality}"
    )

    # ------------------------------------------------------------------------
    # FORECASTS
    # ------------------------------------------------------------------------

    print()
    print("9. ENSEMBLE FORECASTS")

    print(
        f"   1D  : {result.price_forecast_1d:.4f}"
    )

    print(
        f"   7D  : {result.price_forecast_7d:.4f}"
    )

    print(
        f"   30D : {result.price_forecast_30d:.4f}"
    )

    # ------------------------------------------------------------------------
    # PERSISTENCE
    # ------------------------------------------------------------------------

    prediction_file = (
        PREDICTION_RUN_ROOT
        / f"{SYMBOL}.jsonl"
    )

    print()
    print("10. PREDICTION PERSISTENCE")

    print(
        f"   Expected file: {prediction_file}"
    )

    assert prediction_file.exists()

    assert prediction_file.is_file()

    content = prediction_file.read_text(
        encoding="utf-8"
    ).strip()

    assert content

    lines = [
        line
        for line in content.splitlines()
        if line.strip()
    ]

    assert lines

    # Validate the latest persisted record is valid JSON.
    latest_record = json.loads(
        lines[-1]
    )

    assert isinstance(
        latest_record,
        dict,
    )

    print(
        f"   Records found: {len(lines)}"
    )

    print(
        "   Latest persisted record: VALID JSON"
    )

    # ------------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------------

    print()
    print("=" * 78)
    print("🎉 REAL SIX-MODEL HYBRID E2E TEST PASSED")
    print("=" * 78)

    print()
    print("Verified:")
    print("✅ Real AAPL market data")
    print("✅ ModelLoader")
    print("✅ Real LSTM")
    print("✅ Real ARIMA")
    print("✅ Real Prophet")
    print("✅ Real Random Forest")
    print("✅ Real XGBoost")
    print("✅ Real pretrained FinBERT")
    print("✅ DecisionEngine")
    print("✅ Weighted ensemble")
    print("✅ BUY / HOLD / SELL recommendation")
    print("✅ 1D / 7D / 30D forecasts")
    print("✅ Explainability")
    print("✅ PredictionRun persistence")
    print("=" * 78)
