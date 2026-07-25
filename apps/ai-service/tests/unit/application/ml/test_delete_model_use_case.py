"""Unit tests for DeleteModelUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.ml.delete_model_use_case import DeleteModelCommand, DeleteModelUseCase
from src.domain.ml.entities import ModelVersion
from src.domain.ml.exceptions import ModelVersionNotFoundError
from src.domain.ml.value_objects import ModelFamily, ModelVersionId


class FakeModelRegistryRepository:
    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []

    async def save(self, model_version: ModelVersion) -> None:
        self._versions.append(model_version)

    async def get_by_id(self, model_version_id: ModelVersionId) -> ModelVersion | None:
        return next((v for v in self._versions if v.id == model_version_id), None)

    async def get_active_for_family(self, family: ModelFamily) -> ModelVersion | None:
        return None

    async def list_for_family(self, family: ModelFamily) -> tuple[ModelVersion, ...]:
        return tuple(v for v in self._versions if v.family == family)

    async def delete(self, model_version_id: ModelVersionId) -> bool:
        for index, existing in enumerate(self._versions):
            if existing.id == model_version_id:
                del self._versions[index]
                return True
        return False


def _model_version() -> ModelVersion:
    return ModelVersion.create(
        family="xgboost",
        version_tag="v1",
        training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
        training_data_range_end=datetime(2024, 12, 31, tzinfo=UTC),
        validation_metrics={"accuracy": 0.6},
        artifact_location="/models/xgboost/v1.pkl",
    )


class TestDeleteModelUseCase:
    async def test_deletes_an_existing_model_version(self) -> None:
        repo = FakeModelRegistryRepository()
        version = _model_version()
        await repo.save(version)
        use_case = DeleteModelUseCase(repo)

        await use_case.execute(DeleteModelCommand(model_version_id=str(version.id)))

        assert await repo.get_by_id(version.id) is None

    async def test_raises_not_found_for_an_unknown_id(self) -> None:
        repo = FakeModelRegistryRepository()
        use_case = DeleteModelUseCase(repo)
        unknown_id = str(ModelVersionId.new())

        with pytest.raises(ModelVersionNotFoundError):
            await use_case.execute(DeleteModelCommand(model_version_id=unknown_id))
