"""Unit tests for ModelStatusUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

from src.application.ml.model_status_use_case import (
    ALL_MODEL_FAMILIES,
    ModelStatusUseCase,
)
from src.domain.ml.entities import ModelVersion
from src.domain.ml.value_objects import ModelFamily, ModelVersionId


class FakeModelRegistryRepository:
    """
    In-memory fake implementation of ModelRegistryRepository.

    IMPORTANT:
    ModelVersion is symbol-aware, so active-model lookup must use:

        family + symbol

    rather than family alone.
    """

    def __init__(self) -> None:
        self._versions: list[ModelVersion] = []

    async def save(
        self,
        model_version: ModelVersion,
    ) -> None:
        """Save or replace a model version."""

        for index, existing in enumerate(self._versions):
            if existing.id == model_version.id:
                self._versions[index] = model_version
                return

        self._versions.append(model_version)

    async def get_by_id(
        self,
        model_version_id: ModelVersionId,
    ) -> ModelVersion | None:
        """Return a model version by ID."""

        return next(
            (
                version
                for version in self._versions
                if version.id == model_version_id
            ),
            None,
        )

    async def get_active_for_family(
        self,
        family: ModelFamily,
    ) -> ModelVersion | None:
        """
        Return the newest active model for a family.

        This method remains for ModelStatusUseCase compatibility.
        """

        active = [
            version
            for version in self._versions
            if version.family == family
            and version.status == "active"
        ]

        if not active:
            return None

        return max(
            active,
            key=lambda version: version.trained_at,
        )

    async def get_active_for_family_and_symbol(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> ModelVersion | None:
        """
        Return the newest active model for:

            family + symbol

        This is required by ModelLoader and RetrainModelUseCase.
        """

        normalized_symbol = symbol.upper().strip()

        active = [
            version
            for version in self._versions
            if (
                version.family == family
                and version.symbol.upper().strip()
                == normalized_symbol
                and version.status == "active"
            )
        ]

        if not active:
            return None

        return max(
            active,
            key=lambda version: version.trained_at,
        )

    async def list_for_family(
        self,
        family: ModelFamily,
    ) -> tuple[ModelVersion, ...]:
        """Return all versions belonging to a model family."""

        return tuple(
            version
            for version in self._versions
            if version.family == family
        )

    async def delete(
        self,
        model_version_id: ModelVersionId,
    ) -> bool:
        """Delete a model version by ID."""

        for index, existing in enumerate(self._versions):
            if existing.id == model_version_id:
                del self._versions[index]
                return True

        return False


def _model_version(
    family: ModelFamily,
    symbol: str = "AAPL",
) -> ModelVersion:
    """
    Build a valid symbol-aware ModelVersion for tests.
    """

    return ModelVersion.create(
        family=family,
        symbol=symbol,
        version_tag="v1",
        training_data_range_start=datetime(
            2024,
            1,
            1,
            tzinfo=UTC,
        ),
        training_data_range_end=datetime(
            2024,
            12,
            31,
            tzinfo=UTC,
        ),
        validation_metrics={
            "rmse": 1.2,
        },
        artifact_location=(
            f"/models/{family}/{symbol}/v1.pkl"
        ),
    )


class TestModelStatusUseCase:

    async def test_returns_a_status_entry_for_all_six_required_families(
        self,
    ) -> None:
        repo = FakeModelRegistryRepository()

        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        assert len(statuses) == 6

        assert {
            status.family
            for status in statuses
        } == set(ALL_MODEL_FAMILIES)

    async def test_reports_none_active_version_when_untrained(
        self,
    ) -> None:
        repo = FakeModelRegistryRepository()

        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        assert all(
            status.active_version is None
            for status in statuses
        )

        assert all(
            status.version_count == 0
            for status in statuses
        )

    async def test_reports_the_active_version_when_trained(
        self,
    ) -> None:
        repo = FakeModelRegistryRepository()

        await repo.save(
            _model_version("xgboost")
        )

        use_case = ModelStatusUseCase(repo)

        statuses = await use_case.execute()

        xgboost_status = next(
            status
            for status in statuses
            if status.family == "xgboost"
        )

        assert xgboost_status.active_version is not None

        assert xgboost_status.version_count == 1

    async def test_active_lookup_is_symbol_aware(
        self,
    ) -> None:
        """
        A model trained for AAPL must never be returned for TSLA.
        """

        repo = FakeModelRegistryRepository()

        aapl_model = _model_version(
            "xgboost",
            "AAPL",
        )

        tsla_model = _model_version(
            "xgboost",
            "TSLA",
        )

        await repo.save(aapl_model)
        await repo.save(tsla_model)

        aapl_active = (
            await repo.get_active_for_family_and_symbol(
                "xgboost",
                "AAPL",
            )
        )

        tsla_active = (
            await repo.get_active_for_family_and_symbol(
                "xgboost",
                "TSLA",
            )
        )

        assert aapl_active is not None
        assert tsla_active is not None

        assert aapl_active.symbol == "AAPL"
        assert tsla_active.symbol == "TSLA"

        assert aapl_active.id == aapl_model.id
        assert tsla_active.id == tsla_model.id

    async def test_symbol_lookup_is_case_insensitive(
        self,
    ) -> None:
        repo = FakeModelRegistryRepository()

        model = _model_version(
            "xgboost",
            "AAPL",
        )

        await repo.save(model)

        result = (
            await repo.get_active_for_family_and_symbol(
                "xgboost",
                "aapl",
            )
        )

        assert result is not None
        assert result.id == model.id
        assert result.symbol == "AAPL"