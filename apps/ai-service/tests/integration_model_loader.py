from __future__ import annotations

import asyncio
from pathlib import Path

from src.infrastructure.ml.model_registry.file_system_model_registry_repository import (
    FileSystemModelRegistryRepository,
)
from src.infrastructure.ml.model_registry.model_loader import ModelLoader


async def main() -> None:
    print("=" * 78)
    print("INVEST IQ - REAL MODEL LOADER TEST")
    print("=" * 78)

    project_root = Path(__file__).resolve().parents[1]

    registry_root = project_root / "data" / "model_registry"
    artifact_root = project_root / "data" / "models"

    print(f"Registry root : {registry_root}")
    print(f"Artifact root : {artifact_root}")
    print()

    if not registry_root.exists():
        raise RuntimeError(
            f"Model registry does not exist: {registry_root}"
        )

    if not artifact_root.exists():
        raise RuntimeError(
            f"Model artifact directory does not exist: {artifact_root}"
        )

    repository = FileSystemModelRegistryRepository(
        storage_root=registry_root
    )

    loader = ModelLoader(
        model_registry_repository=repository,
        artifact_root=artifact_root,
    )

    print("Loading AAPL models...")
    print()

    models = await loader.load_all_models("AAPL")

    expected_families = (
        "lstm",
        "arima",
        "prophet",
        "random_forest",
        "xgboost",
        "finbert",
    )

    failures: list[str] = []

    for family in expected_families:
        model = models.get(family)

        if model is None:
            print(f"❌ {family:15} -> NOT LOADED")
            failures.append(family)
        else:
            print(
                f"✅ {family:15} -> "
                f"{type(model).__name__}"
            )

    print()
    print("=" * 78)

    if failures:
        print("❌ MODEL LOADING FAILED")
        print()
        print("Missing models:")

        for family in failures:
            print(f"  - {family}")

        print("=" * 78)

        raise RuntimeError(
            "One or more model families failed to load: "
            + ", ".join(failures)
        )

    print("✅ ALL SIX MODEL FAMILIES LOADED")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())