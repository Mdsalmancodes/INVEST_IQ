"""
Filesystem-backed Model Registry repository.

INVEST IQ
=========

Stores ModelVersion metadata as JSON files.

Directory structure:

    <storage_root>/
        <family>/
            <model_version_id>.json

The actual trained model artifact is stored separately by
the model wrapper.

IMPORTANT
=========

ModelVersion is SYMBOL-AWARE.

Therefore active-model lookup is performed using:

    model family + stock symbol

This prevents:

    AAPL LSTM

from accidentally being loaded when:

    TSLA LSTM

was requested.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domain.ml.entities import ModelVersion
from src.domain.ml.value_objects import (
    ModelFamily,
    ModelVersionId,
)


class FileSystemModelRegistryRepository:
    """
    Filesystem implementation of ModelRegistryRepository.
    """

    def __init__(
        self,
        storage_root: str | Path,
    ) -> None:
        self._root = Path(storage_root)

    # ========================================================================
    # SAVE
    # ========================================================================

    async def save(
        self,
        model_version: ModelVersion,
    ) -> None:
        """
        Persist one ModelVersion as JSON.
        """

        family_dir = (
            self._root
            / model_version.family
        )

        family_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        path = (
            family_dir
            / f"{model_version.id}.json"
        )

        path.write_text(
            json.dumps(
                _to_json_dict(model_version),
                indent=2,
            ),
            encoding="utf-8",
        )

    # ========================================================================
    # GET BY ID
    # ========================================================================

    async def get_by_id(
        self,
        model_version_id: ModelVersionId,
    ) -> ModelVersion | None:
        """
        Retrieve a ModelVersion by ID.
        """

        if not self._root.exists():
            return None

        for family_dir in self._root.iterdir():

            if not family_dir.is_dir():
                continue

            candidate = (
                family_dir
                / f"{model_version_id}.json"
            )

            if candidate.exists():
                return _from_json_dict(
                    json.loads(
                        candidate.read_text(
                            encoding="utf-8"
                        )
                    )
                )

        return None

    # ========================================================================
    # GET ACTIVE MODEL BY FAMILY
    # ========================================================================

    async def get_active_for_family(
        self,
        family: ModelFamily,
    ) -> ModelVersion | None:
        """
        Return the newest active model for a family.

        This method is retained for repository compatibility.

        Symbol-specific production model loading should use:

            get_active_for_family_and_symbol()
        """

        versions = await self.list_for_family(
            family
        )

        active = [
            version
            for version in versions
            if version.status == "active"
        ]

        if not active:
            return None

        return max(
            active,
            key=lambda version: version.trained_at,
        )

    # ========================================================================
    # GET ACTIVE MODEL BY FAMILY + SYMBOL
    # ========================================================================

    async def get_active_for_family_and_symbol(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> ModelVersion | None:
        """
        Return the newest active model for:

            family + symbol

        Example:

            lstm + AAPL

        must return only an AAPL LSTM model.

        It must never return TSLA, MSFT, NVDA, etc.
        """

        normalized_symbol = (
            symbol.upper().strip()
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol must not be empty."
            )

        versions = await self.list_for_family(
            family
        )

        matching = [
            version
            for version in versions
            if (
                version.status == "active"
                and version.symbol.upper().strip()
                == normalized_symbol
            )
        ]

        if not matching:
            return None

        return max(
            matching,
            key=lambda version: version.trained_at,
        )

    # ========================================================================
    # LIST FAMILY
    # ========================================================================

    async def list_for_family(
        self,
        family: ModelFamily,
    ) -> tuple[ModelVersion, ...]:
        """
        List all registered versions for a model family.
        """

        family_dir = (
            self._root
            / family
        )

        if not family_dir.exists():
            return ()

        versions: list[ModelVersion] = []

        for path in sorted(
            family_dir.glob("*.json")
        ):
            try:
                data = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                versions.append(
                    _from_json_dict(data)
                )

            except Exception:
                # A corrupt registry record should not
                # silently become a valid ModelVersion.
                raise

        return tuple(versions)

    # ========================================================================
    # DELETE
    # ========================================================================

    async def delete(
        self,
        model_version_id: ModelVersionId,
    ) -> bool:
        """
        Delete one ModelVersion registry record.

        Returns:

            True  -> deleted
            False -> not found
        """

        if not self._root.exists():
            return False

        for family_dir in self._root.iterdir():

            if not family_dir.is_dir():
                continue

            candidate = (
                family_dir
                / f"{model_version_id}.json"
            )

            if candidate.exists():
                candidate.unlink()
                return True

        return False


# ============================================================================
# SERIALIZATION
# ============================================================================


def _to_json_dict(
    model_version: ModelVersion,
) -> dict[str, Any]:
    """
    Convert ModelVersion into JSON-compatible data.
    """

    data: dict[str, Any] = asdict(
        model_version
    )

    data["id"] = str(
        model_version.id
    )

    data["trained_at"] = (
        model_version.trained_at.isoformat()
    )

    data["training_data_range_start"] = (
        model_version
        .training_data_range_start
        .isoformat()
    )

    data["training_data_range_end"] = (
        model_version
        .training_data_range_end
        .isoformat()
    )

    return data


def _from_json_dict(
    data: dict[str, Any],
) -> ModelVersion:
    """
    Reconstruct ModelVersion from JSON data.

    Symbol is mandatory for the current
    symbol-aware ModelVersion architecture.
    """

    symbol = data.get("symbol")

    if not symbol:
        raise ValueError(
            "Model registry record is missing "
            "'symbol'."
        )

    return ModelVersion(
        id=ModelVersionId.from_string(
            data["id"]
        ),
        family=data["family"],
        symbol=symbol.upper().strip(),
        version_tag=data["version_tag"],
        trained_at=datetime.fromisoformat(
            data["trained_at"]
        ),
        training_data_range_start=(
            datetime.fromisoformat(
                data[
                    "training_data_range_start"
                ]
            )
        ),
        training_data_range_end=(
            datetime.fromisoformat(
                data[
                    "training_data_range_end"
                ]
            )
        ),
        validation_metrics=data[
            "validation_metrics"
        ],
        status=data["status"],
        artifact_location=data[
            "artifact_location"
        ],
        rollout_percentage=data.get(
            "rollout_percentage",
            100,
        ),
    )