"""
INVEST IQ - REAL LSTM TRAINING E2E TEST

End-to-end verification:

    Real Yahoo Finance OHLCV
            ↓
    MarketDataRepository
            ↓
    TrainModelUseCase
            ↓
    Real closing prices
            ↓
    LSTM sequences
            ↓
    Chronological validation
            ↓
    LSTM training
            ↓
    Validation metrics
            ↓
    .pt model artifact
            ↓
    ModelVersion
            ↓
    FileSystemModelRegistryRepository
            ↓
    Active LSTM model

No synthetic OHLCV data is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ml.train_model_use_case import (
    TrainModelCommand,
    TrainModelUseCase,
)

from src.infrastructure.http.market_data_repository import (
    MarketDataRepository,
)

from src.infrastructure.ml.model_registry.file_system_model_registry_repository import (
    FileSystemModelRegistryRepository,
)

from src.infrastructure.ml.models.lstm_model import (
    LstmModel,
    LOOKBACK_WINDOW,
)


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

pytestmark = pytest.mark.slow


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"
MODEL_FAMILY = "lstm"
LOOKBACK_DAYS = 400


# ============================================================================
# PATHS
# ============================================================================

AI_SERVICE_ROOT = Path(__file__).resolve().parents[2]

ARTIFACT_ROOT = (
    AI_SERVICE_ROOT
    / "data"
    / "models"
)

REGISTRY_ROOT = (
    AI_SERVICE_ROOT
    / "data"
    / "model_registry"
)


# ============================================================================
# REAL END-TO-END TEST
# ============================================================================


@pytest.mark.asyncio
async def test_lstm_real_training_end_to_end() -> None:
    """
    Train LSTM using real AAPL market data and verify:

    1. Real market data can be downloaded.
    2. Training use case executes successfully.
    3. ModelVersion is created.
    4. Validation metrics are generated.
    5. LSTM .pt artifact exists.
    6. Artifact is non-empty.
    7. Artifact can be loaded.
    8. LSTM history requirement is valid.
    9. ModelVersion is registered.
    10. Active AAPL LSTM model exists.
    11. Registry metadata matches the trained model.
    """

    print()
    print("=" * 78)
    print("INVEST IQ - REAL LSTM TRAINING E2E TEST")
    print("=" * 78)

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    print()
    print("CONFIGURATION")
    print("-" * 78)

    print(f"SYMBOL          : {SYMBOL}")
    print(f"MODEL FAMILY    : {MODEL_FAMILY}")
    print(f"LOOKBACK DAYS   : {LOOKBACK_DAYS}")
    print(f"LSTM WINDOW     : {LOOKBACK_WINDOW}")
    print(f"ARTIFACT ROOT   : {ARTIFACT_ROOT}")
    print(f"REGISTRY ROOT   : {REGISTRY_ROOT}")

    # ========================================================================
    # CREATE ARTIFACT DIRECTORY
    # ========================================================================

    ARTIFACT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("Artifact directory ready.")

    # ========================================================================
    # 1. MARKET DATA REPOSITORY
    # ========================================================================

    print()
    print("=" * 78)
    print("1. MARKET DATA REPOSITORY")
    print("=" * 78)

    market_data_repository = MarketDataRepository()

    print("MarketDataRepository created.")

    # ========================================================================
    # 2. MODEL REGISTRY
    # ========================================================================

    print()
    print("=" * 78)
    print("2. MODEL REGISTRY")
    print("=" * 78)

    registry_repository = FileSystemModelRegistryRepository()

    print(
        "FileSystemModelRegistryRepository created."
    )

    # ========================================================================
    # 3. TRAINING USE CASE
    # ========================================================================

    print()
    print("=" * 78)
    print("3. TRAINING USE CASE")
    print("=" * 78)

    train_use_case = TrainModelUseCase(
        market_data_repository=market_data_repository,
        model_registry_repository=registry_repository,
        artifact_storage_root=ARTIFACT_ROOT,
    )

    print("TrainModelUseCase created.")

    # ========================================================================
    # 4. TRAINING COMMAND
    # ========================================================================

    print()
    print("=" * 78)
    print("4. TRAINING COMMAND")
    print("=" * 78)

    command = TrainModelCommand(
        family=MODEL_FAMILY,
        symbol=SYMBOL,
        lookback_days=LOOKBACK_DAYS,
    )

    print(f"Family         : {command.family}")
    print(f"Symbol         : {command.symbol}")
    print(
        f"Lookback       : {command.lookback_days} calendar days"
    )

    print()
    print(
        "Real Yahoo Finance OHLCV data will be used."
    )

    print(
        "LSTM will consume the real closing-price series."
    )

    print(
        f"LSTM sequence window: {LOOKBACK_WINDOW}"
    )

    # ========================================================================
    # 5. EXECUTE REAL TRAINING
    # ========================================================================

    print()
    print("=" * 78)
    print("5. STARTING REAL LSTM TRAINING")
    print("=" * 78)

    print()
    print("Real market data will be downloaded.")
    print("LSTM training will begin.")
    print()

    result = await train_use_case.execute(command)

    # ========================================================================
    # 6. TRAINING RESULT
    # ========================================================================

    print()
    print("=" * 78)
    print("6. TRAINING RESULT")
    print("=" * 78)

    assert result is not None, (
        "Training use case returned None."
    )

    assert result.model_version is not None, (
        "Training completed but no ModelVersion was returned."
    )

    model_version = result.model_version

    print("Training use case returned successfully.")

    # ========================================================================
    # 7. MODEL VERSION
    # ========================================================================

    print()
    print("=" * 78)
    print("7. MODEL VERSION")
    print("=" * 78)

    print(f"ID                 : {model_version.id}")
    print(f"Family             : {model_version.family}")
    print(f"Symbol             : {model_version.symbol}")
    print(f"Version Tag        : {model_version.version_tag}")
    print(f"Status             : {model_version.status}")
    print(f"Trained At         : {model_version.trained_at}")
    print(
        f"Training Start     : "
        f"{model_version.training_data_range_start}"
    )
    print(
        f"Training End       : "
        f"{model_version.training_data_range_end}"
    )
    print(
        f"Artifact Location  : "
        f"{model_version.artifact_location}"
    )
    print(
        f"Rollout Percentage : "
        f"{model_version.rollout_percentage}%"
    )

    # ========================================================================
    # 8. VALIDATION METRICS
    # ========================================================================

    print()
    print("=" * 78)
    print("8. VALIDATION METRICS")
    print("=" * 78)

    metrics = result.validation_metrics

    assert metrics, (
        "LSTM training completed but no validation metrics were returned."
    )

    for metric_name, metric_value in metrics.items():
        print(
            f"{metric_name:25} : {metric_value}"
        )

    # ========================================================================
    # 9. MODEL VERSION VALIDATION
    # ========================================================================

    print()
    print("=" * 78)
    print("9. MODEL VERSION VALIDATION")
    print("=" * 78)

    assert model_version.family == MODEL_FAMILY, (
        "ModelVersion family does not match LSTM."
    )

    print("Model family is correct.")

    assert model_version.symbol == SYMBOL, (
        "ModelVersion symbol does not match AAPL."
    )

    print("Model symbol is correct.")

    assert model_version.version_tag, (
        "ModelVersion version_tag is empty."
    )

    print("Version tag exists.")

    assert model_version.status == "active", (
        "Newly trained LSTM model is expected to be active."
    )

    print("Model status is active.")

    # ========================================================================
    # 10. ARTIFACT VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)
    print("10. LSTM ARTIFACT VERIFICATION")
    print("=" * 78)

    artifact_path = Path(
        model_version.artifact_location
    )

    print()
    print("Artifact path:")
    print(f"  {artifact_path}")

    assert artifact_path.exists(), (
        "LSTM model artifact does not exist."
    )

    print("Artifact exists.")

    assert artifact_path.is_file(), (
        "LSTM artifact path is not a file."
    )

    print("Artifact is a file.")

    artifact_size = artifact_path.stat().st_size

    assert artifact_size > 0, (
        "LSTM artifact exists but is empty."
    )

    print(
        f"Artifact size: {artifact_size:,} bytes"
    )

    assert artifact_path.suffix.lower() == ".pt", (
        "LSTM artifact must have .pt extension."
    )

    print("Artifact extension is .pt.")

    # ========================================================================
    # 11. DIRECT LSTM ARTIFACT LOAD
    # ========================================================================

    print()
    print("=" * 78)
    print("11. DIRECT LSTM ARTIFACT LOAD")
    print("=" * 78)

    loaded_model = LstmModel.load(
        artifact_path
    )

    assert loaded_model is not None, (
        "LSTM artifact could not be loaded."
    )

    print("LSTM artifact loaded successfully.")

    print(
        f"Loaded model type: "
        f"{type(loaded_model).__name__}"
    )

    # ========================================================================
    # 12. LSTM HISTORY VALIDATION
    # ========================================================================

    print()
    print("=" * 78)
    print("12. LSTM HISTORY VALIDATION")
    print("=" * 78)

    assert loaded_model.has_sufficient_history(
        LOOKBACK_WINDOW * 2
    ), (
        "Loaded LSTM model failed its history requirement."
    )

    print(
        "LSTM history requirement is valid."
    )

    print(
        f"Sequence lookback window: {LOOKBACK_WINDOW}"
    )

    # ========================================================================
    # 13. MODEL REGISTRY VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)
    print("13. MODEL REGISTRY VERIFICATION")
    print("=" * 78)

    registered = await registry_repository.get_by_id(
        model_version.id
    )

    assert registered is not None, (
        "LSTM ModelVersion was not found in filesystem registry."
    )

    print(
        "ModelVersion found in filesystem registry."
    )

    print(f"Registered ID       : {registered.id}")
    print(f"Registered Family   : {registered.family}")
    print(f"Registered Symbol   : {registered.symbol}")
    print(f"Registered Version  : {registered.version_tag}")
    print(f"Registered Status   : {registered.status}")
    print(
        f"Registered Artifact : "
        f"{registered.artifact_location}"
    )

    # ========================================================================
    # 14. ACTIVE MODEL
    # ========================================================================

    print()
    print("=" * 78)
    print("14. ACTIVE LSTM MODEL VERIFICATION")
    print("=" * 78)

    active_model = await (
        registry_repository.get_active_for_family_and_symbol(
            MODEL_FAMILY,
            SYMBOL,
        )
    )

    assert active_model is not None, (
        "No active LSTM model found for AAPL."
    )

    print("Active LSTM model found.")

    print(f"Active Family       : {active_model.family}")
    print(f"Active Symbol       : {active_model.symbol}")
    print(f"Active Version      : {active_model.version_tag}")
    print(f"Active Status       : {active_model.status}")
    print(
        f"Active Artifact     : "
        f"{active_model.artifact_location}"
    )

    # ========================================================================
    # 15. REGISTRY CONSISTENCY
    # ========================================================================

    print()
    print("=" * 78)
    print("15. REGISTRY CONSISTENCY")
    print("=" * 78)

    assert registered.id == model_version.id
    print("ID matches.")

    assert registered.family == MODEL_FAMILY
    print("Family matches.")

    assert registered.symbol == SYMBOL
    print("Symbol matches.")

    assert registered.version_tag == model_version.version_tag
    print("Version matches.")

    assert registered.status == "active"
    print("Registered model is active.")

    assert (
        registered.artifact_location
        == model_version.artifact_location
    )
    print("Artifact location matches.")

    # ========================================================================
    # 16. ACTIVE MODEL CONSISTENCY
    # ========================================================================

    print()
    print("=" * 78)
    print("16. ACTIVE MODEL CONSISTENCY")
    print("=" * 78)

    assert active_model.family == MODEL_FAMILY
    print("Active family matches LSTM.")

    assert active_model.symbol == SYMBOL
    print("Active symbol matches AAPL.")

    assert active_model.status == "active"
    print("Active model status is active.")

    assert (
        active_model.version_tag
        == model_version.version_tag
    )
    print("Active version matches newly trained version.")

    assert (
        active_model.artifact_location
        == model_version.artifact_location
    )
    print("Active artifact location matches.")

    # ========================================================================
    # 17. FINAL PIPELINE
    # ========================================================================

    print()
    print("=" * 78)
    print("17. FINAL LSTM TRAINING PIPELINE")
    print("=" * 78)

    print()
    print("REAL AAPL MARKET DATA")
    print("        ↓")
    print("MARKET DATA REPOSITORY")
    print("        ↓")
    print("REAL CLOSING PRICES")
    print("        ↓")
    print(f"{LOOKBACK_WINDOW}-STEP LSTM SEQUENCES")
    print("        ↓")
    print("CHRONOLOGICAL VALIDATION")
    print("        ↓")
    print("LSTM")
    print("        ↓")
    print("VALIDATION METRICS")
    print("        ↓")
    print("MODEL ARTIFACT (.pt)")
    print("        ↓")
    print("MODEL VERSION")
    print("        ↓")
    print("FILESYSTEM MODEL REGISTRY")
    print("        ↓")
    print("ACTIVE AAPL LSTM MODEL")

    print()
    print("=" * 78)
    print("LSTM END-TO-END TRAINING TEST PASSED")
    print("=" * 78)

    print()
    print("REAL AAPL DATA USED")
    print("LSTM TRAINED")
    print("VALIDATION METRICS GENERATED")
    print(".PT ARTIFACT CREATED")
    print("LSTM ARTIFACT LOAD VERIFIED")
    print("MODEL VERSION CREATED")
    print("MODEL VERSION REGISTERED")
    print("ACTIVE AAPL LSTM MODEL FOUND")
    print("REGISTRY CONSISTENCY VERIFIED")

    print()
    print(
        "INVEST IQ LSTM MODEL IS TRAINED AND REGISTERED."
    )

    print("=" * 78)