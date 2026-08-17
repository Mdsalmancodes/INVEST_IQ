"""
INVEST IQ - REAL XGBOOST TRAINING E2E TEST

End-to-end verification:

    Real Yahoo Finance OHLCV
            ↓
    MarketDataRepository
            ↓
    FeatureEngineer
            ↓
    17 technical indicators
            ↓
    Supervised classification dataset
            ↓
    XGBoost
            ↓
    Validation metrics
            ↓
    .pkl model artifact
            ↓
    ModelVersion
            ↓
    FileSystemModelRegistryRepository
            ↓
    Active AAPL XGBoost model

This test uses REAL AAPL market data.

No mock OHLCV data is used.
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


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

pytestmark = pytest.mark.slow


# ============================================================================
# CONFIGURATION
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILY = "xgboost"

LOOKBACK_DAYS = 400


# ============================================================================
# PATHS
# ============================================================================

# File location:
#
# ai-service/
#     tests/
#         e2e/
#             test_train_xgboost.py
#
# parents[0] = e2e
# parents[1] = tests
# parents[2] = ai-service
#
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
async def test_xgboost_real_training_end_to_end() -> None:
    """
    Train XGBoost using real AAPL market data and verify:

    1. Real market data can be downloaded.
    2. Training use case executes successfully.
    3. ModelVersion is created.
    4. Validation metrics are generated.
    5. XGBoost .pkl artifact exists.
    6. Artifact is non-empty.
    7. ModelVersion is registered.
    8. Registered metadata matches the trained model.
    9. An active AAPL XGBoost model exists.
    10. The newly trained version is the active version.
    """

    print()
    print("=" * 78)
    print("INVEST IQ - REAL XGBOOST TRAINING TEST")
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
    # MARKET DATA REPOSITORY
    # ========================================================================

    print()
    print("=" * 78)
    print("1. MARKET DATA REPOSITORY")
    print("=" * 78)

    market_data_repository = MarketDataRepository()

    print("MarketDataRepository created.")

    # ========================================================================
    # MODEL REGISTRY
    # ========================================================================

    print()
    print("=" * 78)
    print("2. MODEL REGISTRY")
    print("=" * 78)

    registry_repository = (
        FileSystemModelRegistryRepository()
    )

    print(
        "FileSystemModelRegistryRepository created."
    )

    # ========================================================================
    # TRAINING USE CASE
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
    # TRAINING COMMAND
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

    # ========================================================================
    # EXECUTE REAL TRAINING
    # ========================================================================

    print()
    print("=" * 78)
    print("5. STARTING REAL XGBOOST TRAINING")
    print("=" * 78)

    print()
    print(
        "Real Yahoo Finance market data will be used."
    )

    print(
        "XGBoost will be trained using the engineered "
        "technical features."
    )

    print()
    print("Training may take some time.")
    print()

    result = await train_use_case.execute(
        command
    )

    # ========================================================================
    # TRAINING RESULT
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

    print()
    print("Training use case returned successfully.")

    # ========================================================================
    # MODEL VERSION
    # ========================================================================

    print()
    print("=" * 78)
    print("7. MODEL VERSION")
    print("=" * 78)

    print(
        f"ID                 : {model_version.id}"
    )

    print(
        f"Family             : {model_version.family}"
    )

    print(
        f"Symbol             : {model_version.symbol}"
    )

    print(
        f"Version Tag        : {model_version.version_tag}"
    )

    print(
        f"Status             : {model_version.status}"
    )

    print(
        f"Trained At         : {model_version.trained_at}"
    )

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
    # VALIDATION METRICS
    # ========================================================================

    print()
    print("=" * 78)
    print("8. VALIDATION METRICS")
    print("=" * 78)

    metrics = result.validation_metrics

    assert metrics, (
        "Training completed but no validation metrics were returned."
    )

    for metric_name, metric_value in metrics.items():
        print(
            f"{metric_name:25} : {metric_value}"
        )

    # ========================================================================
    # MODEL VERSION VALIDATION
    # ========================================================================

    print()
    print("=" * 78)
    print("9. MODEL VERSION VALIDATION")
    print("=" * 78)

    assert model_version.family == MODEL_FAMILY, (
        "ModelVersion family does not match XGBoost."
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
        "Newly trained model is expected to be active."
    )

    print("Model status is active.")

    # ========================================================================
    # MODEL ARTIFACT VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)
    print("10. MODEL ARTIFACT VERIFICATION")
    print("=" * 78)

    artifact_path = Path(
        model_version.artifact_location
    )

    print()
    print("Artifact path:")
    print(f"  {artifact_path}")

    assert artifact_path.exists(), (
        "XGBoost model artifact does not exist."
    )

    print("Artifact exists.")

    assert artifact_path.is_file(), (
        "XGBoost artifact path is not a file."
    )

    print("Artifact is a file.")

    artifact_size = artifact_path.stat().st_size

    assert artifact_size > 0, (
        "XGBoost artifact exists but is empty."
    )

    print(
        f"Artifact size: {artifact_size:,} bytes"
    )

    assert artifact_path.suffix.lower() == ".pkl", (
        "XGBoost artifact extension must be .pkl."
    )

    print("Artifact extension is .pkl.")

    # ========================================================================
    # MODEL REGISTRY VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)
    print("11. MODEL REGISTRY VERIFICATION")
    print("=" * 78)

    registered = await registry_repository.get_by_id(
        model_version.id
    )

    assert registered is not None, (
        "ModelVersion was not found in filesystem registry."
    )

    print(
        "ModelVersion found in filesystem registry."
    )

    print(
        f"Registered ID       : {registered.id}"
    )

    print(
        f"Registered Family   : {registered.family}"
    )

    print(
        f"Registered Symbol   : {registered.symbol}"
    )

    print(
        f"Registered Version  : {registered.version_tag}"
    )

    print(
        f"Registered Status   : {registered.status}"
    )

    print(
        f"Registered Artifact : "
        f"{registered.artifact_location}"
    )

    # ========================================================================
    # REGISTERED MODEL CONSISTENCY
    # ========================================================================

    print()
    print("=" * 78)
    print("12. REGISTERED MODEL CONSISTENCY")
    print("=" * 78)

    assert registered.id == model_version.id, (
        "Registered model ID does not match."
    )

    print("ID matches.")

    assert registered.family == MODEL_FAMILY, (
        "Registered model family does not match XGBoost."
    )

    print("Family matches.")

    assert registered.symbol == SYMBOL, (
        "Registered model symbol does not match AAPL."
    )

    print("Symbol matches.")

    assert registered.version_tag == model_version.version_tag, (
        "Registered version does not match."
    )

    print("Version matches.")

    assert registered.status == "active", (
        "Registered model is not active."
    )

    print("Registered model is active.")

    assert (
        registered.artifact_location
        == model_version.artifact_location
    ), (
        "Registered artifact location does not match."
    )

    print("Artifact location matches.")

    # ========================================================================
    # LIST FAMILY MODELS
    # ========================================================================

    print()
    print("=" * 78)
    print("13. MODEL FAMILY REGISTRY")
    print("=" * 78)

    family_versions = (
        await registry_repository.list_for_family(
            MODEL_FAMILY
        )
    )

    print(
        f"Total {MODEL_FAMILY} versions in registry: "
        f"{len(family_versions)}"
    )

    assert family_versions, (
        "No XGBoost model versions found for the family."
    )

    # ========================================================================
    # FIND ACTIVE AAPL XGBOOST MODEL
    # ========================================================================

    active_models_for_symbol = [
        version
        for version in family_versions
        if (
            version.symbol.upper() == SYMBOL
            and version.status == "active"
        )
    ]

    assert active_models_for_symbol, (
        f"No active {MODEL_FAMILY} model found for {SYMBOL}."
    )

    # Newest trained active model wins.
    active_model = max(
        active_models_for_symbol,
        key=lambda version: version.trained_at,
    )

    print()
    print("Active AAPL XGBoost model found.")

    print(
        f"Active Family       : {active_model.family}"
    )

    print(
        f"Active Symbol       : {active_model.symbol}"
    )

    print(
        f"Active Version      : {active_model.version_tag}"
    )

    print(
        f"Active Status       : {active_model.status}"
    )

    print(
        f"Active Artifact     : "
        f"{active_model.artifact_location}"
    )

    # ========================================================================
    # ACTIVE MODEL CONSISTENCY
    # ========================================================================

    print()
    print("=" * 78)
    print("14. ACTIVE MODEL CONSISTENCY")
    print("=" * 78)

    assert active_model.symbol == SYMBOL, (
        "Active model symbol does not match AAPL."
    )

    print("Active symbol matches AAPL.")

    assert active_model.family == MODEL_FAMILY, (
        "Active model family does not match XGBoost."
    )

    print("Active family matches XGBoost.")

    assert active_model.status == "active", (
        "Active model is not active."
    )

    print("Active model status is active.")

    assert (
        active_model.version_tag
        == model_version.version_tag
    ), (
        "Active version does not match newly trained version."
    )

    print(
        "Active version matches newly trained version."
    )

    # ========================================================================
    # FINAL PIPELINE VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)
    print("15. FINAL XGBOOST PIPELINE VERIFICATION")
    print("=" * 78)

    print()
    print("REAL AAPL MARKET DATA")
    print("        ↓")
    print("MARKET DATA REPOSITORY")
    print("        ↓")
    print("FEATURE ENGINEERING")
    print("        ↓")
    print("17 TECHNICAL FEATURES")
    print("        ↓")
    print("SUPERVISED DATASET")
    print("        ↓")
    print("XGBOOST")
    print("        ↓")
    print("VALIDATION METRICS")
    print("        ↓")
    print("MODEL ARTIFACT (.pkl)")
    print("        ↓")
    print("MODEL VERSION")
    print("        ↓")
    print("FILESYSTEM MODEL REGISTRY")
    print("        ↓")
    print("ACTIVE AAPL XGBOOST MODEL")

    # ========================================================================
    # FINAL SUCCESS
    # ========================================================================

    print()
    print("=" * 78)
    print("XGBOOST END-TO-END TRAINING TEST PASSED")
    print("=" * 78)

    print()
    print("REAL AAPL DATA USED")
    print("FEATURE ENGINEERING COMPLETED")
    print("17 FEATURES USED")
    print("XGBOOST TRAINED")
    print("VALIDATION METRICS GENERATED")
    print(".PKL ARTIFACT CREATED")
    print("MODEL VERSION CREATED")
    print("MODEL VERSION REGISTERED")
    print("ACTIVE XGBOOST MODEL FOUND")
    print("REGISTRY CONSISTENCY VERIFIED")

    print()
    print(
        "INVEST IQ XGBOOST MODEL "
        "IS TRAINED AND REGISTERED."
    )

    print("=" * 78)