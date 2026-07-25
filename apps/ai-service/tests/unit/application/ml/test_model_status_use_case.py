"""Unit tests for ModelStatusUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

from src.application.ml.model_status_use_case import ALL_MODEL_FAMILIES, ModelStatusUseCase
from src.domain.ml.entities import ModelVersion
from src.domain.ml.value_objects import ModelFamily, ModelVersionId


class FakeModelRegistryRepository:
    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []

    async def save(self, model_version: ModelVersion) -> None:
        for index, existing in enumerate(self._versions):
            if existing.id == model_version.id:
                self._versions[index] = model_version
                return
        self._versions.append(model_version)

    async def get_by_id(self, model_version_id: ModelVersionId) -> ModelVersion | None:
        return next((v for v in self._versions if v.id == model_version_id), None)

    async def get_active_for_family(self, family: ModelFamily) -> ModelVersion | None:
        active = [v for v in self._versions if v.family == family and v.status == "active"]
        return max(active, key=lambda v: v.trained_at) if active else None

    async def list_for_family(self, family: ModelFamily) -> tuple[ModelVersion, ...]:
        return tuple(v for v in self._versions if v.family == family)

    async def delete(self, model_version_id: ModelVersionId) -> bool:
        for index, existing in enumerate(self._versions):
            if existing.id == model_version_id:
                del self._versions[index]
                return True
        return False


def _model_version(family: ModelFamily) -> ModelVersion:
    return ModelVersion.create(
        family=family,
        version_tag="v1",
        training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
        training_data_range_end=datetime(2024, 12, 31, tzinfo=UTC),
        validation_metrics={"rmse": 1.2},
        artifact_location=f"/models/{family}/v1.pkl",
    )


class TestModelStatusUseCase:
    async def test_returns_a_status_entry_for_all_six_required_families(self) -> None:
        repo = FakeModelRegistryRepository()
        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        assert len(statuses) == 6
        assert {s.family for s in statuses} == set(ALL_MODEL_FAMILIES)

    async def test_reports_none_active_version_when_untrained(self) -> None:
        repo = FakeModelRegistryRepository()
        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        assert all(s.active_version is None for s in statuses)
        assert all(s.version_count == 0 for s in statuses)

    async def test_reports_the_active_version_when_trained(self) -> None:
        repo = FakeModelRegistryRepository()
        await repo.save(_model_version("xgboost"))
        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        xgboost_status = next(s for s in statuses if s.family == "xgboost")
        assert xgboost_status.active_version is not None
        assert xgboost_status.version_count == 1
