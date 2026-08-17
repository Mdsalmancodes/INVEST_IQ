import asyncio

from src.config import get_settings
from src.presentation.dependencies.ml_use_cases import (
    get_model_registry_repository,
    get_model_loader,
)


async def main():
    settings = get_settings()

    repository = get_model_registry_repository(settings)

    loader = get_model_loader(
        settings=settings,
        model_registry_repository=repository,
    )

    print()
    print('=' * 80)
    print('INVEST IQ MODEL LOADER TEST')
    print('SYMBOL: AAPL')
    print('=' * 80)

    result = await loader.load_all_models('AAPL')

    print()
    print('LOADED MODELS')
    print('-' * 80)

    for family, model in result.models.items():
        model_name = (
            type(model).__name__
            if model is not None
            else 'NONE'
        )

        print(
            f'{family:15} -> {model_name}'
        )

    print()
    print('MODEL VERSION IDS')
    print('-' * 80)

    for family, version_id in result.model_version_ids.items():
        print(
            f'{family:15} -> {version_id}'
        )

    print()
    print('SUMMARY')
    print('-' * 80)

    loaded = [
        family
        for family, model in result.models.items()
        if model is not None
    ]

    missing = [
        family
        for family, model in result.models.items()
        if model is None
    ]

    print(
        'Loaded :',
        ', '.join(loaded) if loaded else 'NONE',
    )

    print(
        'Missing:',
        ', '.join(missing) if missing else 'NONE',
    )

    print()
    print('=' * 80)
    print('TEST COMPLETE')
    print('=' * 80)


asyncio.run(main())