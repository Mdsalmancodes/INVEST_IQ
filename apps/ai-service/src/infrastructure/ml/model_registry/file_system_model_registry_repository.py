"""
Filesystem Model Registry Repository
====================================

INVEST IQ

This repository stores ModelVersion metadata on the local filesystem.

Responsibilities
----------------

    ModelVersion
        ↓
    Filesystem Model Registry
        ↓
    JSON metadata

The repository does NOT store trained model weights.

Model artifacts are stored separately:

    data/models/
        lstm/
            AAPL/
                <version>.pt

        arima/
            AAPL/
                <version>.pkl

        prophet/
            AAPL/
                <version>.pkl

        random_forest/
            AAPL/
                <version>.pkl

        xgboost/
            AAPL/
                <version>.pkl


Registry metadata is stored separately:

    data/model_registry/
        lstm/
            <model-version-id>.json

        arima/
            <model-version-id>.json

        prophet/
            <model-version-id>.json

        random_forest/
            <model-version-id>.json

        xgboost/
            <model-version-id>.json


Supported operations
--------------------

    save()
    get_by_id()
    list_for_family()
    get_active_for_family()
    get_active_for_family_and_symbol()
    delete()
    repair_active_versions()


ACTIVE VERSION RULE
-------------------

For every:

    model_family + symbol

there must be exactly ONE active ModelVersion.

Example:

    lstm + AAPL

can have:

    20260813 -> archived
    20260814 -> active

but must NEVER have:

    20260813 -> active
    20260814 -> active


The repository automatically enforces this rule whenever an
active ModelVersion is saved.

IMPORTANT
---------

Archiving a registry entry does NOT delete its trained model artifact.

For example:

    registry:
        20260813 -> archived

    artifact:
        data/models/lstm/AAPL/20260813.pt

The artifact remains available for:

    - historical lineage
    - rollback
    - auditing
    - reproducibility
"""


from __future__ import annotations

import json
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
    Filesystem implementation of the INVEST IQ Model Registry.

    The repository is symbol-aware.

    Therefore:

        random_forest + AAPL

    is completely different from:

        random_forest + TSLA


    ACTIVE VERSION INVARIANT
    ------------------------

    For each:

        family + symbol

    there can be only one active version.

    When a new active version is saved, all other active versions
    for the same family + symbol are automatically changed to
    archived in the registry metadata.
    """

    # ======================================================================
    # CONSTANTS
    # ======================================================================

    ACTIVE_STATUS = "active"
    ARCHIVED_STATUS = "archived"

    # ======================================================================
    # INITIALIZATION
    # ======================================================================

    def __init__(
        self,
        storage_root: str | Path | None = None,
    ) -> None:
        """
        Initialize the filesystem registry.

        If storage_root is not supplied, the repository automatically
        resolves:

            apps/ai-service/data/model_registry
        """

        if storage_root is None:

            # Current file:
            #
            # src/
            #   infrastructure/
            #     ml/
            #       model_registry/
            #         file_system_model_registry_repository.py
            #
            # parents[0] = model_registry
            # parents[1] = ml
            # parents[2] = infrastructure
            # parents[3] = src
            # parents[4] = ai-service

            ai_service_root = (
                Path(__file__)
                .resolve()
                .parents[4]
            )

            storage_root = (
                ai_service_root
                / "data"
                / "model_registry"
            )

        self._root = Path(
            storage_root
        ).resolve()

        self._root.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ======================================================================
    # SAVE
    # ======================================================================

    async def save(
        self,
        model_version: ModelVersion,
    ) -> None:
        """
        Save a ModelVersion to the filesystem.

        ACTIVE VERSION RULE
        --------------------

        If the incoming ModelVersion is active:

            family + symbol
                    ↓
            find all existing active versions
                    ↓
            archive them
                    ↓
            save incoming version as active

        Therefore:

            AAPL + LSTM

        can only have:

            ONE active version.

        Existing model artifacts are NEVER deleted.

        This method is safe when saving the same ModelVersion ID again.
        The current version is excluded from the archival operation.
        """

        if model_version is None:
            raise ValueError(
                "model_version must not be None."
            )

        # --------------------------------------------------------------
        # Normalize identity fields
        # --------------------------------------------------------------

        family = self._normalize_family(
            model_version.family
        )

        symbol = self._normalize_symbol(
            model_version.symbol
        )

        status = self._normalize_status(
            model_version.status
        )

        # --------------------------------------------------------------
        # Validate required fields
        # --------------------------------------------------------------

        if not family:
            raise ValueError(
                "ModelVersion family must not be empty."
            )

        if not symbol:
            raise ValueError(
                "ModelVersion symbol must not be empty."
            )

        if not status:
            raise ValueError(
                "ModelVersion status must not be empty."
            )

        # --------------------------------------------------------------
        # Ensure family directory exists
        # --------------------------------------------------------------

        family_directory = (
            self._root / family
        )

        family_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        # --------------------------------------------------------------
        # Enforce single-active-version invariant
        # --------------------------------------------------------------

        if status == self.ACTIVE_STATUS:

            await self._archive_other_active_versions(
                family=family,
                symbol=symbol,
                keep_model_version_id=str(
                    model_version.id
                ),
            )

        # --------------------------------------------------------------
        # Build destination
        # --------------------------------------------------------------

        file_path = (
            family_directory
            / f"{model_version.id}.json"
        )

        # --------------------------------------------------------------
        # Serialize
        # --------------------------------------------------------------

        data = self._serialize_model_version(
            model_version
        )

        # --------------------------------------------------------------
        # Guarantee normalized registry values
        # --------------------------------------------------------------

        data["family"] = family
        data["symbol"] = symbol
        data["status"] = status

        # --------------------------------------------------------------
        # Atomic write
        # --------------------------------------------------------------

        self._atomic_write_json(
            file_path=file_path,
            data=data,
        )

    # ======================================================================
    # ARCHIVE OTHER ACTIVE VERSIONS
    # ======================================================================

    async def _archive_other_active_versions(
        self,
        family: str,
        symbol: str,
        keep_model_version_id: str | None = None,
    ) -> int:
        """
        Archive every active version for:

            family + symbol

        except keep_model_version_id.

        Returns
        -------

        Number of registry entries changed.

        IMPORTANT
        ---------

        Only registry metadata is changed.

        Trained model artifacts are NOT deleted.
        """

        normalized_family = (
            self._normalize_family(
                family
            )
        )

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        if not normalized_family:
            raise ValueError(
                "family must not be empty."
            )

        if not normalized_symbol:
            raise ValueError(
                "symbol must not be empty."
            )

        family_directory = (
            self._root
            / normalized_family
        )

        if not family_directory.exists():
            return 0

        if not family_directory.is_dir():
            return 0

        archived_count = 0

        for file_path in sorted(
            family_directory.glob("*.json")
        ):

            # ----------------------------------------------------------
            # Read existing version
            # ----------------------------------------------------------

            existing = self._read_model_version(
                file_path
            )

            existing_family = (
                self._normalize_family(
                    existing.family
                )
            )

            existing_symbol = (
                self._normalize_symbol(
                    existing.symbol
                )
            )

            existing_status = (
                self._normalize_status(
                    existing.status
                )
            )

            existing_id = str(
                existing.id
            )

            # ----------------------------------------------------------
            # Same family?
            # ----------------------------------------------------------

            if (
                existing_family
                != normalized_family
            ):
                continue

            # ----------------------------------------------------------
            # Same symbol?
            # ----------------------------------------------------------

            if (
                existing_symbol
                != normalized_symbol
            ):
                continue

            # ----------------------------------------------------------
            # Same version?
            # ----------------------------------------------------------

            if (
                keep_model_version_id is not None
                and existing_id
                == str(
                    keep_model_version_id
                )
            ):
                continue

            # ----------------------------------------------------------
            # Only archive active versions
            # ----------------------------------------------------------

            if (
                existing_status
                != self.ACTIVE_STATUS
            ):
                continue

            # ----------------------------------------------------------
            # Convert existing metadata to archived
            # ----------------------------------------------------------

            archived_data = (
                self._serialize_model_version(
                    existing
                )
            )

            archived_data["family"] = (
                normalized_family
            )

            archived_data["symbol"] = (
                normalized_symbol
            )

            archived_data["status"] = (
                self.ARCHIVED_STATUS
            )

            # ----------------------------------------------------------
            # Atomic update
            # ----------------------------------------------------------

            self._atomic_write_json(
                file_path=file_path,
                data=archived_data,
            )

            archived_count += 1

        # --------------------------------------------------------------
        # Logging
        # --------------------------------------------------------------

        if archived_count > 0:

            print(
                "MODEL REGISTRY ACTIVE VERSION CLEANUP"
            )

            print(
                f"   Family: {normalized_family}"
            )

            print(
                f"   Symbol: {normalized_symbol}"
            )

            print(
                f"   Archived versions: {archived_count}"
            )

        return archived_count

    # ======================================================================
    # GET BY ID
    # ======================================================================

    async def get_by_id(
        self,
        model_version_id: ModelVersionId,
    ) -> ModelVersion | None:
        """
        Find a ModelVersion by ID.

        Searches all model-family directories.
        """

        if model_version_id is None:
            raise ValueError(
                "model_version_id must not be None."
            )

        if not self._root.exists():
            return None

        filename = (
            f"{model_version_id}.json"
        )

        for family_directory in (
            self._root.iterdir()
        ):

            if not family_directory.is_dir():
                continue

            file_path = (
                family_directory
                / filename
            )

            if not file_path.exists():
                continue

            return self._read_model_version(
                file_path
            )

        return None

    # ======================================================================
    # LIST FAMILY
    # ======================================================================

    async def list_for_family(
        self,
        family: ModelFamily,
    ) -> tuple[ModelVersion, ...]:
        """
        Return every registered model version for a model family.
        """

        normalized_family = (
            self._normalize_family(
                family
            )
        )

        if not normalized_family:
            raise ValueError(
                "family must not be empty."
            )

        family_directory = (
            self._root
            / normalized_family
        )

        if not family_directory.exists():
            return ()

        if not family_directory.is_dir():
            return ()

        versions: list[
            ModelVersion
        ] = []

        for file_path in sorted(
            family_directory.glob("*.json")
        ):

            versions.append(
                self._read_model_version(
                    file_path
                )
            )

        return tuple(
            versions
        )

    # ======================================================================
    # GET ACTIVE FOR FAMILY
    # ======================================================================

    async def get_active_for_family(
        self,
        family: ModelFamily,
    ) -> ModelVersion | None:
        """
        Return the newest active model for a model family.

        This method is NOT symbol-specific.

        For multi-stock prediction, prefer:

            get_active_for_family_and_symbol()
        """

        versions = await (
            self.list_for_family(
                family
            )
        )

        active_versions = [
            version
            for version in versions
            if (
                self._normalize_status(
                    version.status
                )
                == self.ACTIVE_STATUS
            )
        ]

        if not active_versions:
            return None

        # Safety fallback for legacy registry data.
        return max(
            active_versions,
            key=lambda version: version.trained_at,
        )

    # ======================================================================
    # GET ACTIVE FOR FAMILY + SYMBOL
    # ======================================================================

    async def get_active_for_family_and_symbol(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> ModelVersion | None:
        """
        Return the active model for:

            model family + stock symbol

        Example:

            random_forest + AAPL

        must never return:

            random_forest + TSLA

        Safety behavior
        ---------------

        Normally there should be exactly one active version.

        If historical registry data contains multiple active entries,
        the newest trained version is returned.

        repair_active_versions() can then permanently repair the
        registry.
        """

        normalized_family = (
            self._normalize_family(
                family
            )
        )

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        if not normalized_family:
            raise ValueError(
                "family must not be empty."
            )

        if not normalized_symbol:
            raise ValueError(
                "symbol must not be empty."
            )

        versions = await (
            self.list_for_family(
                normalized_family
            )
        )

        active_versions = [
            version
            for version in versions
            if (
                self._normalize_status(
                    version.status
                )
                == self.ACTIVE_STATUS
                and self._normalize_symbol(
                    version.symbol
                )
                == normalized_symbol
            )
        ]

        if not active_versions:
            return None

        # --------------------------------------------------------------
        # Safety fallback for legacy duplicate-active data
        # --------------------------------------------------------------

        return max(
            active_versions,
            key=lambda version: version.trained_at,
        )

    # ======================================================================
    # REPAIR ACTIVE VERSIONS
    # ======================================================================

    async def repair_active_versions(
        self,
        family: ModelFamily | None = None,
        symbol: str | None = None,
    ) -> int:
        """
        Repair historical registry data.

        This is useful when older registry entries were created before
        the single-active-version rule existed.

        Examples
        --------

        Repair everything:

            await repository.repair_active_versions()

        Repair one family:

            await repository.repair_active_versions(
                family="lstm"
            )

        Repair one symbol:

            await repository.repair_active_versions(
                symbol="AAPL"
            )

        Repair one family + symbol:

            await repository.repair_active_versions(
                family="lstm",
                symbol="AAPL"
            )

        For each family + symbol combination:

            newest active version
                    ↓
                remains active

            older active versions
                    ↓
                become archived

        Returns
        -------

        Number of registry entries changed.
        """

        normalized_family = (
            self._normalize_family(
                family
            )
            if family is not None
            else None
        )

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
            if symbol is not None
            else None
        )

        # --------------------------------------------------------------
        # Validate filters
        # --------------------------------------------------------------

        if (
            normalized_family is not None
            and not normalized_family
        ):
            raise ValueError(
                "family must not be empty."
            )

        if (
            normalized_symbol is not None
            and not normalized_symbol
        ):
            raise ValueError(
                "symbol must not be empty."
            )

        if not self._root.exists():
            return 0

        repaired_count = 0

        # --------------------------------------------------------------
        # Determine families
        # --------------------------------------------------------------

        if normalized_family is not None:

            families = (
                normalized_family,
            )

        else:

            families = tuple(
                directory.name
                for directory in self._root.iterdir()
                if directory.is_dir()
            )

        # --------------------------------------------------------------
        # Inspect each family
        # --------------------------------------------------------------

        for family_name in families:

            versions = await (
                self.list_for_family(
                    family_name
                )
            )

            # ----------------------------------------------------------
            # Group active versions by symbol
            # ----------------------------------------------------------

            active_by_symbol: dict[
                str,
                list[ModelVersion],
            ] = {}

            for version in versions:

                if (
                    self._normalize_status(
                        version.status
                    )
                    != self.ACTIVE_STATUS
                ):
                    continue

                version_symbol = (
                    self._normalize_symbol(
                        version.symbol
                    )
                )

                if not version_symbol:
                    continue

                if (
                    normalized_symbol is not None
                    and version_symbol
                    != normalized_symbol
                ):
                    continue

                active_by_symbol.setdefault(
                    version_symbol,
                    [],
                ).append(
                    version
                )

            # ----------------------------------------------------------
            # Repair each duplicate group
            # ----------------------------------------------------------

            for (
                symbol_name,
                active_versions,
            ) in active_by_symbol.items():

                if len(active_versions) <= 1:
                    continue

                # ------------------------------------------------------
                # Newest trained version remains active
                # ------------------------------------------------------

                active_to_keep = max(
                    active_versions,
                    key=lambda version: version.trained_at,
                )

                # ------------------------------------------------------
                # Archive every older active version
                # ------------------------------------------------------

                for version in active_versions:

                    if (
                        str(version.id)
                        == str(
                            active_to_keep.id
                        )
                    ):
                        continue

                    file_path = (
                        self._root
                        / family_name
                        / f"{version.id}.json"
                    )

                    archived_data = (
                        self._serialize_model_version(
                            version
                        )
                    )

                    archived_data["family"] = (
                        self._normalize_family(
                            version.family
                        )
                    )

                    archived_data["symbol"] = (
                        self._normalize_symbol(
                            version.symbol
                        )
                    )

                    archived_data["status"] = (
                        self.ARCHIVED_STATUS
                    )

                    self._atomic_write_json(
                        file_path=file_path,
                        data=archived_data,
                    )

                    repaired_count += 1

                print(
                    "MODEL REGISTRY REPAIRED"
                )

                print(
                    f"   Family: {family_name}"
                )

                print(
                    f"   Symbol: {symbol_name}"
                )

                print(
                    "   Kept active: "
                    f"{active_to_keep.id}"
                )

        # --------------------------------------------------------------
        # Final summary
        # --------------------------------------------------------------

        if repaired_count > 0:

            print(
                "MODEL REGISTRY REPAIR COMPLETE"
            )

            print(
                f"   Archived entries: {repaired_count}"
            )

        return repaired_count

    # ======================================================================
    # DELETE
    # ======================================================================

    async def delete(
        self,
        model_version_id: ModelVersionId,
    ) -> bool:
        """
        Delete registry metadata.

        IMPORTANT

        This deletes ONLY the JSON registry entry.

        It does NOT delete the trained model artifact.
        """

        if model_version_id is None:
            raise ValueError(
                "model_version_id must not be None."
            )

        if not self._root.exists():
            return False

        filename = (
            f"{model_version_id}.json"
        )

        for family_directory in (
            self._root.iterdir()
        ):

            if not family_directory.is_dir():
                continue

            file_path = (
                family_directory
                / filename
            )

            if not file_path.exists():
                continue

            file_path.unlink()

            return True

        return False

    # ======================================================================
    # SERIALIZATION
    # ======================================================================

    @staticmethod
    def _serialize_model_version(
        model_version: ModelVersion,
    ) -> dict[str, Any]:
        """
        Convert ModelVersion into JSON-compatible data.
        """

        return {
            "id": str(
                model_version.id
            ),

            "family": (
                str(
                    model_version.family
                )
                .lower()
                .strip()
            ),

            "symbol": (
                str(
                    model_version.symbol
                )
                .upper()
                .strip()
            ),

            "version_tag": str(
                model_version.version_tag
            ),

            "trained_at": (
                model_version
                .trained_at
                .isoformat()
            ),

            "training_data_range_start": (
                model_version
                .training_data_range_start
                .isoformat()
            ),

            "training_data_range_end": (
                model_version
                .training_data_range_end
                .isoformat()
            ),

            "validation_metrics": {
                str(key): float(value)
                for key, value
                in model_version
                .validation_metrics
                .items()
            },

            "status": (
                str(
                    model_version.status
                )
                .lower()
                .strip()
            ),

            "artifact_location": str(
                model_version.artifact_location
            ),

            "rollout_percentage": int(
                model_version
                .rollout_percentage
            ),
        }

    # ======================================================================
    # DESERIALIZATION
    # ======================================================================

    @staticmethod
    def _deserialize_model_version(
        data: dict[str, Any],
    ) -> ModelVersion:
        """
        Convert JSON data back into ModelVersion.
        """

        # --------------------------------------------------------------
        # Required fields
        # --------------------------------------------------------------

        required_fields = (
            "id",
            "family",
            "symbol",
            "version_tag",
            "trained_at",
            "training_data_range_start",
            "training_data_range_end",
            "validation_metrics",
            "status",
            "artifact_location",
        )

        missing_fields = [
            field
            for field in required_fields
            if field not in data
        ]

        if missing_fields:
            raise ValueError(
                "Registry entry is missing required fields: "
                + ", ".join(
                    missing_fields
                )
            )

        # --------------------------------------------------------------
        # ID
        # --------------------------------------------------------------

        model_version_id = (
            ModelVersionId.from_string(
                str(
                    data["id"]
                )
            )
        )

        # --------------------------------------------------------------
        # FAMILY
        # --------------------------------------------------------------

        family = (
            str(
                data["family"]
            )
            .lower()
            .strip()
        )

        if not family:
            raise ValueError(
                "Registry ModelVersion family must not be empty."
            )

        # --------------------------------------------------------------
        # SYMBOL
        # --------------------------------------------------------------

        symbol = (
            str(
                data["symbol"]
            )
            .upper()
            .strip()
        )

        if not symbol:
            raise ValueError(
                "Registry ModelVersion symbol must not be empty."
            )

        # --------------------------------------------------------------
        # DATETIME
        # --------------------------------------------------------------

        trained_at = (
            datetime.fromisoformat(
                str(
                    data["trained_at"]
                )
            )
        )

        training_start = (
            datetime.fromisoformat(
                str(
                    data[
                        "training_data_range_start"
                    ]
                )
            )
        )

        training_end = (
            datetime.fromisoformat(
                str(
                    data[
                        "training_data_range_end"
                    ]
                )
            )
        )

        # --------------------------------------------------------------
        # Validate training range
        # --------------------------------------------------------------

        if training_start > training_end:
            raise ValueError(
                "training_data_range_start must not be after "
                "training_data_range_end."
            )

        # --------------------------------------------------------------
        # METRICS
        # --------------------------------------------------------------

        raw_metrics = data[
            "validation_metrics"
        ]

        if not isinstance(
            raw_metrics,
            dict,
        ):
            raise TypeError(
                "validation_metrics must be a JSON object."
            )

        validation_metrics = {
            str(key): float(value)
            for key, value
            in raw_metrics.items()
        }

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        status = (
            str(
                data["status"]
            )
            .lower()
            .strip()
        )

        if not status:
            raise ValueError(
                "Registry ModelVersion status must not be empty."
            )

        # --------------------------------------------------------------
        # ARTIFACT LOCATION
        # --------------------------------------------------------------

        artifact_location = str(
            data["artifact_location"]
        )

        if not artifact_location.strip():
            raise ValueError(
                "Registry ModelVersion artifact_location "
                "must not be empty."
            )

        # --------------------------------------------------------------
        # ROLLOUT
        # --------------------------------------------------------------

        rollout_percentage = int(
            data.get(
                "rollout_percentage",
                100,
            )
        )

        if not 0 <= rollout_percentage <= 100:
            raise ValueError(
                "rollout_percentage must be between 0 and 100."
            )

        # --------------------------------------------------------------
        # CREATE ENTITY
        # --------------------------------------------------------------

        return ModelVersion(
            id=model_version_id,

            family=family,

            symbol=symbol,

            version_tag=str(
                data["version_tag"]
            ),

            trained_at=trained_at,

            training_data_range_start=(
                training_start
            ),

            training_data_range_end=(
                training_end
            ),

            validation_metrics=(
                validation_metrics
            ),

            status=status,

            artifact_location=(
                artifact_location
            ),

            rollout_percentage=(
                rollout_percentage
            ),
        )

    # ======================================================================
    # READ FILE
    # ======================================================================

    @classmethod
    def _read_model_version(
        cls,
        file_path: Path,
    ) -> ModelVersion:
        """
        Read one ModelVersion JSON file.
        """

        try:

            raw_text = (
                file_path.read_text(
                    encoding="utf-8"
                )
            )

            data = json.loads(
                raw_text
            )

            if not isinstance(
                data,
                dict,
            ):
                raise ValueError(
                    "Registry JSON root must be an object."
                )

            return cls._deserialize_model_version(
                data
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Invalid JSON in model registry file: "
                f"{file_path}"
            ) from exc

        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise RuntimeError(
                "Failed to load ModelVersion from registry file: "
                f"{file_path}"
            ) from exc

    # ======================================================================
    # NORMALIZATION HELPERS
    # ======================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        """
        Normalize stock symbol.

        Example:

            " aapl "
                ↓
            "AAPL"
        """

        if symbol is None:
            return ""

        return (
            str(symbol)
            .upper()
            .strip()
        )

    @staticmethod
    def _normalize_family(
        family: Any,
    ) -> str:
        """
        Normalize model family.

        Example:

            " Random_Forest "
                ↓
            "random_forest"
        """

        if family is None:
            return ""

        return (
            str(family)
            .lower()
            .strip()
        )

    @staticmethod
    def _normalize_status(
        status: Any,
    ) -> str:
        """
        Normalize registry status.

        Example:

            " ACTIVE "
                ↓
            "active"
        """

        if status is None:
            return ""

        return (
            str(status)
            .lower()
            .strip()
        )

    # ======================================================================
    # ATOMIC JSON WRITE
    # ======================================================================

    @staticmethod
    def _atomic_write_json(
        file_path: Path,
        data: dict[str, Any],
    ) -> None:
        """
        Atomically write JSON metadata.

        The JSON is first written to a temporary file and then
        replaced into the final location.

        This reduces the possibility of leaving a partially-written
        registry file if the process is interrupted during a write.
        """

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            file_path.with_name(
                f".{file_path.name}.tmp"
            )
        )

        try:

            temporary_path.write_text(
                json.dumps(
                    data,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            temporary_path.replace(
                file_path
            )

        except Exception:

            if temporary_path.exists():

                try:
                    temporary_path.unlink()

                except OSError:
                    pass

            raise