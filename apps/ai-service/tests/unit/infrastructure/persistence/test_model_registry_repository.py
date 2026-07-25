"""Unit tests for FileSystemModelRegistryRepository."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.ml.entities import ModelVersion
from src.infrastructure.persistence.model_registry_repository import (
    FileSystemModelRegistryRepository,
)


def _model_version(
    family: str = "xgboost",
    version_tag: str = "v1",
    trained_at: datetime | None = None,
) -> ModelVersion:
    version = ModelVersion.create(
        family=family,  # type: ignore[arg-type]
        version_tag=version_tag,
        training_data_range_start=datetime(2024, 1, 1, tzinfo=UTC),
        training_data_range_end=datetime(2024, 12, 31, tzinfo=UTC),
        validation_metrics={"accuracy": 0.62},
        artifact_location=f"/models/{family}/{version_tag}.pkl",
    )
    if trained_at is not None:
        # ModelVersion.create() always stamps datetime.now(UTC) — tests
        # that need two versions with a guaranteed, unambiguous training
        # order must override this directly, since two back-to-back
        # create() calls can land within the same clock tick on Windows
        # (sub-millisecond resolution ties), making get_active_for_family's
        # max()-by-trained_at comparison non-deterministic on ties.
        version.trained_at = trained_at
    return version


class TestFileSystemModelRegistryRepositorySaveAndGet:
    async def test_save_and_get_by_id_round_trips(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        version = _model_version()

        await repo.save(version)
        fetched = await repo.get_by_id(version.id)

        assert fetched is not None
        assert fetched.family == "xgboost"
        assert fetched.version_tag == "v1"
        assert fetched.validation_metrics == {"accuracy": 0.62}

    async def test_get_by_id_returns_none_when_not_found(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        version = _model_version()
        result = await repo.get_by_id(version.id)
        assert result is None


class TestFileSystemModelRegistryRepositoryListForFamily:
    async def test_lists_all_versions_for_a_family(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        v1 = _model_version(version_tag="v1")
        v2 = _model_version(version_tag="v2")
        await repo.save(v1)
        await repo.save(v2)

        versions = await repo.list_for_family("xgboost")

        assert len(versions) == 2
        assert {v.version_tag for v in versions} == {"v1", "v2"}

    async def test_returns_empty_tuple_for_unknown_family(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        versions = await repo.list_for_family("lstm")
        assert versions == ()


class TestFileSystemModelRegistryRepositoryGetActiveForFamily:
    async def test_returns_none_when_no_versions_exist(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        assert await repo.get_active_for_family("lstm") is None

    async def test_returns_the_most_recently_trained_active_version(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        older = _model_version(version_tag="v1", trained_at=datetime(2024, 1, 1, tzinfo=UTC))
        await repo.save(older)
        newer = _model_version(version_tag="v2", trained_at=datetime(2024, 6, 1, tzinfo=UTC))
        await repo.save(newer)

        active = await repo.get_active_for_family("xgboost")

        assert active is not None
        assert active.version_tag == "v2"

    async def test_excludes_retired_versions(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemModelRegistryRepository(tmp_path)
        version = _model_version()
        version.retire()
        await repo.save(version)

        active = await repo.get_active_for_family("xgboost")

        assert active is None
