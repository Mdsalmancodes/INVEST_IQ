from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


# ============================================================================
# PROJECT PATHS
# ============================================================================

# This file lives at:
#
# C:\md_salman\INVEST_IQ\verify_aapl_models.py
#
# Real persistent model storage lives at:
#
# C:\md_salman\INVEST_IQ\data\models
# C:\md_salman\INVEST_IQ\data\model_registry
#
# Docker Compose mounts:
#
#   ./data:/app/data
#
# Therefore PROJECT_ROOT/data is the host-side source of truth.

PROJECT_ROOT = Path(__file__).resolve().parent
AI_SERVICE_ROOT = PROJECT_ROOT / "apps" / "ai-service"
ENV_FILE = AI_SERVICE_ROOT / ".env"

ARTIFACT_ROOT = PROJECT_ROOT / "data" / "models"
REGISTRY_ROOT = PROJECT_ROOT / "data" / "model_registry"


# ============================================================================
# VALIDATE PROJECT STRUCTURE
# ============================================================================

if not AI_SERVICE_ROOT.is_dir():
    raise RuntimeError(
        f"AI-service directory does not exist:\n{AI_SERVICE_ROOT}"
    )

if not ENV_FILE.is_file():
    raise RuntimeError(
        f"AI-service .env file does not exist:\n{ENV_FILE}"
    )

if not ARTIFACT_ROOT.is_dir():
    raise RuntimeError(
        f"Real model artifact directory does not exist:\n{ARTIFACT_ROOT}"
    )

if not REGISTRY_ROOT.is_dir():
    raise RuntimeError(
        f"Real model registry directory does not exist:\n{REGISTRY_ROOT}"
    )


# ============================================================================
# PYTHON IMPORT PATH
# ============================================================================

sys.path.insert(0, str(AI_SERVICE_ROOT))


# ============================================================================
# LOAD ENVIRONMENT
# ============================================================================

try:
    from dotenv import load_dotenv
except ImportError as exc:
    raise RuntimeError(
        "python-dotenv is not installed for this Python interpreter.\n"
        "Install it with:\n"
        '"C:\\Users\\MD SALMAN.A\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" '
        "-m pip install python-dotenv"
    ) from exc


load_dotenv(
    dotenv_path=ENV_FILE,
    override=False,
)


# ============================================================================
# APPLICATION IMPORTS
# ============================================================================

from src.config import get_settings
from src.infrastructure.ml.model_registry.model_loader import ModelLoader
from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)


# ============================================================================
# CONSTANTS
# ============================================================================

SYMBOL = "AAPL"

MODEL_FAMILIES = (
    "lstm",
    "arima",
    "prophet",
    "random_forest",
    "xgboost",
)

ALL_MODEL_FAMILIES = (
    "lstm",
    "arima",
    "prophet",
    "random_forest",
    "xgboost",
    "finbert",
)


# ============================================================================
# HELPERS
# ============================================================================


def print_section(title: str) -> None:
    print()
    print(title)
    print("-" * 78)


def print_environment_value(name: str) -> None:
    value = os.getenv(name)

    if value:
        if any(
            secret_word in name.upper()
            for secret_word in (
                "TOKEN",
                "PASSWORD",
                "SECRET",
                "KEY",
            )
        ):
            display = "***SET***"
        else:
            display = value
    else:
        display = "MISSING"

    print(f"{name:<22}: {display}")


def list_files(directory: Path, suffix: str | None = None) -> list[Path]:
    if not directory.is_dir():
        return []

    files = [
        path
        for path in directory.iterdir()
        if path.is_file()
    ]

    if suffix is not None:
        files = [
            path
            for path in files
            if path.suffix.lower() == suffix.lower()
        ]

    return sorted(
        files,
        key=lambda path: path.name,
    )


# ============================================================================
# MAIN VERIFICATION
# ============================================================================


async def main() -> None:

    print()
    print("=" * 78)
    print("INVEST IQ - REAL AAPL MODEL VERIFICATION")
    print("=" * 78)

    # ========================================================================
    # PYTHON
    # ========================================================================

    print_section("PYTHON")

    print(f"Executable : {sys.executable}")
    print(f"Version    : {sys.version.split()[0]}")

    # ========================================================================
    # PROJECT PATHS
    # ========================================================================

    print_section("PROJECT PATHS")

    print(f"Project root   : {PROJECT_ROOT}")
    print(f"AI-service     : {AI_SERVICE_ROOT}")
    print(f".env           : {ENV_FILE}")

    # ========================================================================
    # SETTINGS
    # ========================================================================

    settings = get_settings()

    print_section("CONFIGURED APPLICATION STORAGE")

    print(
        f"Configured artifact path : "
        f"{settings.ml_artifact_storage_path}"
    )

    print(
        f"Configured registry path : "
        f"{settings.ml_model_registry_storage_path}"
    )

    # ========================================================================
    # REAL HOST STORAGE
    # ========================================================================

    print_section("REAL HOST MODEL STORAGE")

    print(f"Model artifacts : {ARTIFACT_ROOT}")
    print(f"Model registry  : {REGISTRY_ROOT}")

    print()
    print(
        "Docker host storage mapping:"
    )
    print(
        f"  {PROJECT_ROOT / 'data'}"
        "  ->  /app/data"
    )

    # ========================================================================
    # STORAGE CHECK
    # ========================================================================

    print_section("STORAGE CHECK")

    print(
        f"Artifacts directory : "
        f"{'EXISTS' if ARTIFACT_ROOT.is_dir() else 'MISSING'}"
    )

    print(
        f"Registry directory  : "
        f"{'EXISTS' if REGISTRY_ROOT.is_dir() else 'MISSING'}"
    )

    # ========================================================================
    # ENVIRONMENT
    # ========================================================================

    print_section("ENVIRONMENT")

    for name in (
        "ENVIRONMENT",
        "SERVICE_NAME",
        "CORE_API_BASE_URL",
        "REDIS_CACHE_URL",
        "REDIS_BROKER_URL",
    ):
        print_environment_value(name)

    # ========================================================================
    # AAPL ARTIFACT DIRECTORIES
    # ========================================================================

    print_section("AAPL ARTIFACT DIRECTORIES")

    for family in MODEL_FAMILIES:

        family_directory = (
            ARTIFACT_ROOT
            / family
            / SYMBOL
        )

        artifacts = list_files(
            family_directory
        )

        status = (
            "FOUND"
            if artifacts
            else "MISSING"
        )

        print(
            f"{family:<18}: "
            f"{status:<8} "
            f"directory={family_directory}"
        )

        for artifact in artifacts:
            print(
                f"  -> {artifact.name}"
                f"  ({artifact.stat().st_size:,} bytes)"
            )

    # ========================================================================
    # AAPL MODEL REGISTRY
    # ========================================================================

    print_section("AAPL MODEL REGISTRY")

    for family in MODEL_FAMILIES:

        family_directory = (
            REGISTRY_ROOT
            / family
        )

        registry_files = list_files(
            family_directory,
            ".json",
        )

        status = (
            "FOUND"
            if registry_files
            else "MISSING"
        )

        print(
            f"{family:<18}: "
            f"{status:<8} "
            f"registry_files={len(registry_files)}"
        )

        for registry_file in registry_files:
            print(
                f"  -> {registry_file.name}"
            )

    # ========================================================================
    # IMPORTANT: VERIFY THE NEW REAL RANDOM FOREST ARTIFACT EXISTS
    # ========================================================================

    print_section("LATEST RANDOM FOREST ARTIFACT")

    random_forest_directory = (
        ARTIFACT_ROOT
        / "random_forest"
        / SYMBOL
    )

    random_forest_artifacts = list_files(
        random_forest_directory,
        ".pkl",
    )

    if not random_forest_artifacts:
        print(
            "ERROR: No Random Forest artifact exists."
        )
    else:
        latest_random_forest = max(
            random_forest_artifacts,
            key=lambda path: path.stat().st_mtime,
        )

        print(
            f"Latest artifact : "
            f"{latest_random_forest.name}"
        )

        print(
            f"Artifact size   : "
            f"{latest_random_forest.stat().st_size:,} bytes"
        )

        print(
            f"Artifact path   : "
            f"{latest_random_forest}"
        )

    # ========================================================================
    # REAL MODEL REGISTRY
    # ========================================================================

    repository = FileSystemModelRegistryRepository(
        str(REGISTRY_ROOT)
    )

    # ========================================================================
    # REAL MODEL LOADER
    # ========================================================================

    loader = ModelLoader(
        model_registry_repository=repository,
        artifact_root=ARTIFACT_ROOT,
    )

    # ========================================================================
    # LOAD ALL REAL AAPL MODELS
    # ========================================================================

    print_section("LOADING REAL AAPL MODELS")

    loaded = await loader.load_all_models(
        SYMBOL
    )

    # ========================================================================
    # MODEL LOAD STATUS
    # ========================================================================

    print_section("MODEL LOAD STATUS")

    for family in ALL_MODEL_FAMILIES:

        model = loaded.models.get(
            family
        )

        if model is None:
            status = "MISSING"
            model_type = "-"
        else:
            status = "LOADED"
            model_type = type(model).__name__

        print(
            f"{family:<18}: "
            f"{status:<10}: "
            f"{model_type}"
        )

    # ========================================================================
    # MODEL VERSION IDs
    # ========================================================================

    print_section("REGISTERED MODEL VERSION IDs")

    if loaded.model_version_ids:

        for family, version_id in (
            loaded.model_version_ids.items()
        ):
            print(
                f"{family:<18}: {version_id}"
            )

    else:

        print(
            "NO TRAINED MODEL VERSION IDS RETURNED"
        )

    # ========================================================================
    # FINAL VERIFICATION
    # ========================================================================

    print()
    print("=" * 78)

    missing_models = [
        family
        for family in ALL_MODEL_FAMILIES
        if loaded.models.get(family) is None
    ]

    if missing_models:

        print("RESULT: NOT COMPLETE")
        print()

        print("Missing model families:")

        for family in missing_models:
            print(
                f"  - {family}"
            )

        print()
        print("IMPORTANT:")
        print("No fake model was created.")
        print("No dummy prediction was created.")
        print("No model was substituted.")

        print()
        print(
            "The verification failed because one or more "
            "real models could not be loaded."
        )

        print("=" * 78)

        raise SystemExit(1)

    # ========================================================================
    # SUCCESS
    # ========================================================================

    print(
        "RESULT: ALL SIX MODELS LOADED"
    )

    print()
    print(
        "AAPL real model loading verification PASSED."
    )

    print()
    print(
        "REAL TRAINED MODELS:"
    )

    for family in MODEL_FAMILIES:
        print(
            f"  [OK] {family}"
        )

    print()
    print(
        "PRETRAINED MODEL:"
    )

    print(
        "  [OK] finbert"
    )

    print()
    print(
        "No fake model was created."
    )

    print(
        "No dummy model was created."
    )

    print(
        "No model was substituted."
    )

    print("=" * 78)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    asyncio.run(main())