import asyncio

from src.config import get_settings
from src.presentation.dependencies.ml_use_cases import (
    get_model_registry_repository,
)
from src.infrastructure.ml.model_registry.model_loader import ModelLoader


async def main():
    settings = get_settings()

    repository = get_model_registry_repository(settings)

    loader = ModelLoader(
        model_registry_repository=repository,
        artifact_root=settings.ml_artifact_storage_path,
    )

    families = [
        "lstm",
        "arima",
        "prophet",
        "random_forest",
        "xgboost",
        "finbert",
    ]

    print("=" * 70)
    print("INVEST IQ MODEL LOADING TEST")
    print("SYMBOL: AAPL")
    print("=" * 70)

    for family in families:
        print()
        print(f"[{family.upper()}]")

        try:
            model = await loader.load_model(
                family,
                "AAPL",
            )

            if model is None:
                print("RESULT: FAILED / NONE")
            else:
                print("RESULT: LOADED")
                print("TYPE:", type(model).__name__)

        except Exception as exc:
            print("RESULT: ERROR")
            print("ERROR:", type(exc).__name__, str(exc))

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


asyncio.run(main())