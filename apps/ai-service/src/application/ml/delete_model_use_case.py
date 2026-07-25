"""DeleteModelUseCase — backs Phase 8's Admin-only "Delete Models" API
endpoint. Removes a trained ModelVersion's tracking record from the
registry. Deliberately does NOT delete the underlying artifact file on
disk (torch .pt / pickled sklearn/xgboost/statsmodels/prophet model) this
phase — only the registry's metadata record. Removing the tracking record
is sufficient to make the version unreachable via get_active_for_family()/
list_for_family() (the only two read paths any use case or the Decision
Engine ever calls), and leaves the artifact file itself as inert, harmless
disk usage rather than risking a mid-request race where a concurrent
prediction request has already resolved the model's artifact_location and
is mid-load when the file disappears underneath it. A future phase could
add artifact-file cleanup as a separate, explicitly-scheduled sweep once
this ordering concern is designed for.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.ml.exceptions import ModelVersionNotFoundError
from src.domain.ml.repositories import ModelRegistryRepository
from src.domain.ml.value_objects import ModelVersionId


@dataclass(frozen=True, slots=True)
class DeleteModelCommand:
    model_version_id: str


class DeleteModelUseCase:
    def __init__(self, model_registry_repository: ModelRegistryRepository) -> None:
        self._model_registry_repository = model_registry_repository

    async def execute(self, command: DeleteModelCommand) -> None:
        version_id = ModelVersionId.from_string(command.model_version_id)
        deleted = await self._model_registry_repository.delete(version_id)
        if not deleted:
            raise ModelVersionNotFoundError(
                f"No model version found with id {command.model_version_id!r}"
            )
