"""FileSystemModelRegistryRepository — implements
src.domain.ml.repositories.ModelRegistryRepository.

Per Document 4 §10.8's ModelVersion entity: tracks trained artifacts and
their lifecycle. Persists ModelVersion metadata as one JSON file per
version under `<storage_root>/<family>/<version_id>.json` — the actual
trained artifact (torch .pt, pickled sklearn/xgboost/statsmodels/prophet
model) is saved separately by each model wrapper's own save() method, at
the path recorded in `ModelVersion.artifact_location`. This repository
only tracks the metadata/lifecycle record, matching Document 4 §10.8's
description of ModelVersion as a tracking entity, not the artifact
storage mechanism itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.ml.entities import ModelVersion
from src.domain.ml.value_objects import ModelFamily, ModelVersionId


class FileSystemModelRegistryRepository:
    def __init__(self, storage_root: str | Path) -> None:
        self._root = Path(storage_root)

    async def save(self, model_version: ModelVersion) -> None:
        family_dir = self._root / model_version.family
        family_dir.mkdir(parents=True, exist_ok=True)
        path = family_dir / f"{model_version.id}.json"
        path.write_text(json.dumps(_to_json_dict(model_version), indent=2), encoding="utf-8")

    async def get_by_id(self, model_version_id: ModelVersionId) -> ModelVersion | None:
        if not self._root.exists():
            return None
        for family_dir in self._root.iterdir():
            candidate = family_dir / f"{model_version_id}.json"
            if candidate.exists():
                return _from_json_dict(json.loads(candidate.read_text(encoding="utf-8")))
        return None

    async def get_active_for_family(self, family: ModelFamily) -> ModelVersion | None:
        versions = await self.list_for_family(family)
        active = [v for v in versions if v.status == "active"]
        if not active:
            return None
        return max(active, key=lambda v: v.trained_at)

    async def list_for_family(self, family: ModelFamily) -> tuple[ModelVersion, ...]:
        family_dir = self._root / family
        if not family_dir.exists():
            return ()
        versions = [
            _from_json_dict(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted(family_dir.glob("*.json"))
        ]
        return tuple(versions)

    async def delete(self, model_version_id: ModelVersionId) -> bool:
        if not self._root.exists():
            return False
        for family_dir in self._root.iterdir():
            candidate = family_dir / f"{model_version_id}.json"
            if candidate.exists():
                candidate.unlink()
                return True
        return False


def _to_json_dict(model_version: ModelVersion) -> dict[str, Any]:
    data: dict[str, Any] = asdict(model_version)
    data["id"] = str(model_version.id)
    data["trained_at"] = model_version.trained_at.isoformat()
    data["training_data_range_start"] = model_version.training_data_range_start.isoformat()
    data["training_data_range_end"] = model_version.training_data_range_end.isoformat()
    return data


def _from_json_dict(data: dict[str, Any]) -> ModelVersion:
    return ModelVersion(
        id=ModelVersionId.from_string(data["id"]),
        family=data["family"],
        version_tag=data["version_tag"],
        trained_at=datetime.fromisoformat(data["trained_at"]),
        training_data_range_start=datetime.fromisoformat(data["training_data_range_start"]),
        training_data_range_end=datetime.fromisoformat(data["training_data_range_end"]),
        validation_metrics=data["validation_metrics"],
        status=data["status"],
        artifact_location=data["artifact_location"],
        rollout_percentage=data["rollout_percentage"],
    )
