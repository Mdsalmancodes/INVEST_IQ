"""ModelStatusUseCase — backs the "Model Status" API endpoint. Reads
ModelRegistryRepository across all 6 required model families (Document
4 §10.8's ModelVersion lifecycle tracking), so the frontend's "Model
Status" panel can show each family's active version, training date, and
validation metrics in one call.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.ml.entities import ModelVersion
from src.domain.ml.repositories import ModelRegistryRepository
from src.domain.ml.value_objects import ModelFamily

ALL_MODEL_FAMILIES: tuple[ModelFamily, ...] = (
    "lstm",
    "arima",
    "prophet",
    "random_forest",
    "xgboost",
    "finbert",
)
"""Exactly the 6 model families required by the founder's Phase 7
instruction — never a different or reduced set."""


@dataclass(frozen=True, slots=True)
class ModelFamilyStatus:
    family: ModelFamily
    active_version: ModelVersion | None
    version_count: int


class ModelStatusUseCase:
    def __init__(self, model_registry_repository: ModelRegistryRepository) -> None:
        self._model_registry_repository = model_registry_repository

    async def execute(self) -> tuple[ModelFamilyStatus, ...]:
        statuses = []
        for family in ALL_MODEL_FAMILIES:
            active = await self._model_registry_repository.get_active_for_family(family)
            all_versions = await self._model_registry_repository.list_for_family(family)
            statuses.append(
                ModelFamilyStatus(
                    family=family, active_version=active, version_count=len(all_versions)
                )
            )
        return tuple(statuses)
