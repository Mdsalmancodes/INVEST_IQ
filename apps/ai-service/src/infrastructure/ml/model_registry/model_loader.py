"""
ModelLoader — loads trained ML model artifacts for INVEST IQ.

Responsibilities:

    Model Registry
          ↓
    ModelVersion
          ↓
    artifact_location
          ↓
    ModelLoader
          ↓
    trained model instance
          ↓
    DecisionEngine

Supported model families:

    LSTM
    ARIMA
    Prophet
    Random Forest
    XGBoost
    FinBERT

Important:

    This class NEVER trains models.

    LSTM / ARIMA / Prophet / Random Forest / XGBoost
    must already have trained artifacts.

    FinBERT is a pretrained inference-only model.

    Missing models are returned as None so the DecisionEngine
    can operate as a partial ensemble.

Model lineage:

    For trained model families, ModelLoader also returns the
    exact ModelVersion ID from the model registry.

    This ID is later passed to DecisionEngine so that every
    Forecast entity can reference the actual trained model
    version that generated it.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional

from src.domain.ml.repositories import ModelRegistryRepository
from src.domain.ml.value_objects import (
    ModelFamily,
    ModelVersionId,
)

from src.infrastructure.ml.models.arima_model import ArimaModel
from src.infrastructure.ml.models.finbert_model import FinBertModel
from src.infrastructure.ml.models.lstm_model import LstmModel
from src.infrastructure.ml.models.prophet_model import ProphetModel
from src.infrastructure.ml.models.random_forest_model import (
    RandomForestModel,
)
from src.infrastructure.ml.models.xgboost_model import (
    XgboostModel,
)


logger = logging.getLogger(__name__)


# ============================================================================
# LOADED MODEL RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class LoadedModels:
    """
    Complete result of loading the models required for live inference.

    models:
        Loaded model instances keyed by model family.

    model_version_ids:
        Actual ModelVersion IDs from the model registry.

    FinBERT is pretrained and therefore normally has no
    ModelVersion ID in the INVEST IQ training registry.

    All other model families should have a real ModelVersion ID
    whenever their trained artifact is successfully loaded.
    """

    models: dict[
        ModelFamily,
        Optional[object],
    ]

    model_version_ids: dict[
        ModelFamily,
        ModelVersionId,
    ]


# ============================================================================
# MODEL LOADER
# ============================================================================


class ModelLoader:
    """
    Loads the active trained model for a specific model family + symbol.

    Example:

        AAPL
        ├── LSTM          -> trained artifact + ModelVersion ID
        ├── ARIMA         -> trained artifact + ModelVersion ID
        ├── Prophet       -> trained artifact + ModelVersion ID
        ├── Random Forest -> trained artifact + ModelVersion ID
        ├── XGBoost       -> trained artifact + ModelVersion ID
        └── FinBERT       -> pretrained

    A missing individual model does not crash the whole prediction.
    """

    def __init__(
        self,
        model_registry_repository: ModelRegistryRepository,
        artifact_root: str | Path,
    ) -> None:

        self._repo = model_registry_repository

        self._artifact_root = Path(
            artifact_root
        )

        logger.info(
            "ModelLoader initialized",
            extra={
                "artifact_root": str(
                    self._artifact_root
                ),
            },
        )

    # ======================================================================
    # LOAD ONE MODEL
    # ======================================================================

    async def load_model(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> Optional[object]:
        """
        Load one model family for one stock symbol.

        Returns:

            Model instance if available.
            None if unavailable.

        FinBERT is special because it is pretrained and does not have
        a ModelVersion/artifact in our training registry.

        NOTE:

            This method intentionally returns only the model instance.

            load_all_models() additionally returns the exact
            ModelVersion IDs so prediction lineage is preserved.
        """

        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        # ==================================================================
        # FINBERT
        # ==================================================================

        if family == "finbert":

            logger.info(
                "Initializing pretrained FinBERT",
                extra={
                    "symbol": symbol,
                    "family": family,
                },
            )

            try:

                return FinBertModel()

            except Exception:

                logger.exception(
                    "Failed to initialize FinBERT",
                    extra={
                        "symbol": symbol,
                    },
                )

                return None

        # ==================================================================
        # MODEL REGISTRY
        # ==================================================================

        try:

            model_version = (
                await self._repo.get_active_for_family_and_symbol(
                    family,
                    symbol,
                )
            )

        except Exception:

            logger.exception(
                "Failed to query model registry",
                extra={
                    "symbol": symbol,
                    "family": family,
                },
            )

            return None

        # ==================================================================
        # NO ACTIVE MODEL
        # ==================================================================

        if model_version is None:

            logger.warning(
                "No active model found",
                extra={
                    "symbol": symbol,
                    "family": family,
                },
            )

            return None

        # ==================================================================
        # SYMBOL SAFETY CHECK
        # ==================================================================

        registered_symbol = (
            getattr(
                model_version,
                "symbol",
                "",
            )
            .upper()
            .strip()
        )

        if registered_symbol != symbol:

            logger.error(
                "Model symbol mismatch",
                extra={
                    "requested_symbol": symbol,
                    "registered_symbol": registered_symbol,
                    "family": family,
                },
            )

            return None

        # ==================================================================
        # ARTIFACT PATH
        # ==================================================================

        artifact_path = (
            self._resolve_artifact_path(
                model_version.artifact_location
            )
        )

        if artifact_path is None:

            logger.warning(
                "Model artifact does not exist",
                extra={
                    "symbol": symbol,
                    "family": family,
                    "artifact_location": (
                        model_version.artifact_location
                    ),
                },
            )

            return None

        logger.info(
            "Loading trained model artifact",
            extra={
                "symbol": symbol,
                "family": family,
                "artifact_path": str(
                    artifact_path
                ),
                "version": (
                    model_version.version_tag
                ),
                "model_version_id": str(
                    model_version.id.value
                ),
            },
        )

        # ==================================================================
        # LOAD MODEL ARTIFACT
        # ==================================================================

        try:

            if family == "lstm":

                return LstmModel.load(
                    artifact_path
                )

            if family == "arima":

                return ArimaModel.load(
                    artifact_path
                )

            if family == "prophet":

                return ProphetModel.load(
                    artifact_path
                )

            if family == "random_forest":

                return RandomForestModel.load(
                    artifact_path
                )

            if family == "xgboost":

                return XgboostModel.load(
                    artifact_path
                )

            logger.error(
                "Unsupported model family",
                extra={
                    "family": family,
                    "symbol": symbol,
                },
            )

            return None

        except Exception:

            logger.exception(
                "Failed to load model artifact",
                extra={
                    "family": family,
                    "symbol": symbol,
                    "artifact_path": str(
                        artifact_path
                    ),
                    "model_version_id": str(
                        model_version.id.value
                    ),
                },
            )

            return None

    # ======================================================================
    # LOAD ALL SIX MODELS
    # ======================================================================

    async def load_all_models(
        self,
        symbol: str,
    ) -> LoadedModels:
        """
        Load all six model families for one stock.

        FinBERT is pretrained and has no registry ModelVersion ID.

        The five trained model families obtain their real ModelVersion ID
        only when their real artifact successfully loads.
        """

        symbol = symbol.upper().strip()

        if not symbol:
            raise ValueError(
                "symbol must not be empty"
            )

        # ==================================================================
        # ALL SUPPORTED MODEL FAMILIES
        # ==================================================================

        families: tuple[
            ModelFamily,
            ...
        ] = (
            "lstm",
            "arima",
            "prophet",
            "random_forest",
            "xgboost",
            "finbert",
        )

        # ==================================================================
        # RESULT CONTAINERS
        # ==================================================================

        models: dict[
            ModelFamily,
            Optional[object],
        ] = {}

        model_version_ids: dict[
            ModelFamily,
            ModelVersionId,
        ] = {}

        # ==================================================================
        # LOAD EACH MODEL
        # ==================================================================

        for family in families:

            # ==============================================================

            # FINBERT
            # ==============================================================

            if family == "finbert":

                models[family] = (
                    await self.load_model(
                        family=family,
                        symbol=symbol,
                    )
                )

                continue

            # ==============================================================

            # GET ACTIVE REGISTERED MODEL VERSION
            # ==============================================================

            try:

                model_version = (
                    await self._repo.get_active_for_family_and_symbol(
                        family,
                        symbol,
                    )
                )

            except Exception:

                logger.exception(
                    "Failed to query model registry",
                    extra={
                        "symbol": symbol,
                        "family": family,
                    },
                )

                models[family] = None

                continue

            # ==============================================================

            # NO ACTIVE VERSION
            # ==============================================================

            if model_version is None:

                logger.warning(
                    "No active model found",
                    extra={
                        "symbol": symbol,
                        "family": family,
                    },
                )

                models[family] = None

                continue

            # ==============================================================

            # SYMBOL SAFETY CHECK
            # ==============================================================

            registered_symbol = (
                getattr(
                    model_version,
                    "symbol",
                    "",
                )
                .upper()
                .strip()
            )

            if registered_symbol != symbol:

                logger.error(
                    "Model symbol mismatch",
                    extra={
                        "requested_symbol": symbol,
                        "registered_symbol": (
                            registered_symbol
                        ),
                        "family": family,
                    },
                )

                models[family] = None

                continue

            # ==============================================================

            # RESOLVE ARTIFACT
            # ==============================================================

            artifact_path = (
                self._resolve_artifact_path(
                    model_version.artifact_location
                )
            )

            if artifact_path is None:

                logger.warning(
                    "Model artifact does not exist",
                    extra={
                        "symbol": symbol,
                        "family": family,
                        "artifact_location": (
                            model_version.artifact_location
                        ),
                        "model_version_id": str(
                            model_version.id.value
                        ),
                    },
                )

                models[family] = None

                continue

            # ==============================================================

            # LOAD TRAINED ARTIFACT
            # ==============================================================

            try:

                if family == "lstm":

                    model = (
                        LstmModel.load(
                            artifact_path
                        )
                    )

                elif family == "arima":

                    model = (
                        ArimaModel.load(
                            artifact_path
                        )
                    )

                elif family == "prophet":

                    model = (
                        ProphetModel.load(
                            artifact_path
                        )
                    )

                elif family == "random_forest":

                    model = (
                        RandomForestModel.load(
                            artifact_path
                        )
                    )

                elif family == "xgboost":

                    model = (
                        XgboostModel.load(
                            artifact_path
                        )
                    )

                else:

                    logger.error(
                        "Unsupported model family",
                        extra={
                            "family": family,
                            "symbol": symbol,
                        },
                    )

                    model = None

            except Exception:

                logger.exception(
                    "Failed to load model artifact",
                    extra={
                        "family": family,
                        "symbol": symbol,
                        "artifact_path": str(
                            artifact_path
                        ),
                        "model_version_id": str(
                            model_version.id.value
                        ),
                    },
                )

                model = None

            # ==============================================================

            # STORE MODEL
            # ==============================================================

            models[family] = model

            # ==============================================================

            # STORE REAL MODEL VERSION ID
            # ==============================================================

            if model is not None:

                model_version_ids[family] = (
                    model_version.id
                )

                logger.info(
                    "Loaded trained model with registry version",
                    extra={
                        "symbol": symbol,
                        "family": family,
                        "model_version_id": str(
                            model_version.id.value
                        ),
                        "version_tag": (
                            model_version.version_tag
                        ),
                        "artifact_path": str(
                            artifact_path
                        ),
                    },
                )

        # ==================================================================
        # LOADING SUMMARY
        # ==================================================================

        loaded_models = [
            family
            for family, model
            in models.items()
            if model is not None
        ]

        unavailable_models = [
            family
            for family, model
            in models.items()
            if model is None
        ]

        logger.info(
            "Model loading completed",
            extra={
                "symbol": symbol,
                "loaded_models": loaded_models,
                "unavailable_models": unavailable_models,
                "model_version_ids": {
                    family: str(
                        version_id.value
                    )
                    for family, version_id
                    in model_version_ids.items()
                },
            },
        )

        # ==================================================================
        # RETURN COMPLETE RESULT
        # ==================================================================

        return LoadedModels(
            models=models,
            model_version_ids=model_version_ids,
        )

    # ======================================================================
    # ARTIFACT PATH RESOLUTION
    # ======================================================================

    def _resolve_artifact_path(
        self,
        artifact_location: str | Path,
    ) -> Optional[Path]:
        """
        Resolve a model artifact location safely.

        The model registry may contain paths written by different
        execution environments.

        Supported examples:

            Windows absolute:
                C:\\md_salman\\INVEST_IQ\\data\\models\\...

            Docker absolute:
                /app/data/models/...

            Application relative:
                data/models/...

            Artifact-root relative:
                lstm/AAPL/model.pt

        The method ONLY resolves existing files.

        It NEVER creates, copies, modifies, or substitutes artifacts.
        """

        if not artifact_location:
            return None

        try:

            stored = str(
                artifact_location
            ).strip()

            if not stored:
                return None

            artifact_root = (
                self._artifact_root.resolve()
            )

            # --------------------------------------------------------------
            # NORMALIZE SEPARATORS
            # --------------------------------------------------------------

            normalized = stored.replace(
                "\\",
                "/",
            )

            normalized_no_leading = (
                normalized.lstrip("/")
            )

            # --------------------------------------------------------------
            # CANDIDATE PATHS
            # --------------------------------------------------------------

            candidates: list[Path] = []

            # ==============================================================
            # 1. EXACT ABSOLUTE PATH
            # ==============================================================

            stored_path = Path(
                stored
            )

            if stored_path.is_absolute():

                candidates.append(
                    stored_path
                )

            # ==============================================================
            # 2. DOCKER PATH
            #
            # /app/data/models/...
            #
            # maps to:
            #
            # <artifact_root>/...
            # ==============================================================

            docker_prefix = (
                "app/data/models/"
            )

            if normalized_no_leading.startswith(
                docker_prefix
            ):

                relative_from_models = (
                    normalized_no_leading[
                        len(docker_prefix):
                    ]
                )

                if relative_from_models:

                    candidates.append(
                        artifact_root
                        / Path(
                            relative_from_models
                        )
                    )

            # ==============================================================
            # 3. APPLICATION RELATIVE PATH
            #
            # data/models/...
            #
            # maps to:
            #
            # <artifact_root>/...
            # ==============================================================

            data_models_prefix = (
                "data/models/"
            )

            if normalized_no_leading.startswith(
                data_models_prefix
            ):

                relative_from_models = (
                    normalized_no_leading[
                        len(data_models_prefix):
                    ]
                )

                if relative_from_models:

                    candidates.append(
                        artifact_root
                        / Path(
                            relative_from_models
                        )
                    )

            # ==============================================================
            # 4. PATH RELATIVE TO ARTIFACT ROOT
            #
            # Example:
            #
            # lstm/AAPL/model.pt
            # ==============================================================

            if normalized_no_leading:

                candidates.append(
                    artifact_root
                    / Path(
                        normalized_no_leading
                    )
                )

            # ==============================================================
            # 5. PATH CONTAINING THE ARTIFACT ROOT
            #
            # Useful for cases where a registry path contains:
            #
            # .../models/lstm/AAPL/model.pt
            #
            # ==============================================================

            path_parts = Path(
                normalized_no_leading
            ).parts

            # We look for "models" followed by the model family.
            #
            # This avoids depending on the exact operating-system path.
            try:

                models_index = (
                    path_parts.index(
                        "models"
                    )
                )

            except ValueError:

                models_index = -1

            if models_index >= 0:

                remaining_parts = (
                    path_parts[
                        models_index + 1:
                    ]
                )

                if remaining_parts:

                    candidates.append(
                        artifact_root
                        / Path(
                            *remaining_parts
                        )
                    )

            # ==============================================================
            # 6. CHECK ALL CANDIDATES
            # ==============================================================

            checked: set[str] = set()

            for candidate in candidates:

                try:

                    resolved_candidate = (
                        candidate.resolve()
                    )

                except Exception:

                    resolved_candidate = (
                        Path(candidate)
                    )

                key = str(
                    resolved_candidate
                ).lower()

                if key in checked:
                    continue

                checked.add(key)

                if (
                    resolved_candidate.exists()
                    and resolved_candidate.is_file()
                ):

                    logger.info(
                        "Resolved model artifact",
                        extra={
                            "artifact_location": stored,
                            "resolved_path": str(
                                resolved_candidate
                            ),
                        },
                    )

                    return resolved_candidate

            # ==============================================================
            # 7. SAFE FILENAME FALLBACK
            #
            # Only used when the exact path cannot be resolved.
            #
            # This searches the configured artifact root for an EXISTING
            # file with the exact registered filename.
            #
            # No file is created or modified.
            # ==============================================================

            filename = Path(
                normalized
            ).name

            if filename:

                matches = [
                    path
                    for path in artifact_root.rglob(
                        filename
                    )
                    if path.is_file()
                ]

                if len(matches) == 1:

                    resolved_candidate = (
                        matches[0].resolve()
                    )

                    logger.info(
                        "Resolved model artifact by unique filename",
                        extra={
                            "artifact_location": stored,
                            "resolved_path": str(
                                resolved_candidate
                            ),
                        },
                    )

                    return resolved_candidate

                if len(matches) > 1:

                    logger.warning(
                        "Multiple artifacts found with same filename; "
                        "refusing ambiguous resolution",
                        extra={
                            "artifact_location": stored,
                            "filename": filename,
                            "matches": [
                                str(path)
                                for path in matches
                            ],
                        },
                    )

            # ==============================================================
            # NOTHING FOUND
            # ==============================================================

            logger.warning(
                "Model artifact does not exist",
                extra={
                    "artifact_location": stored,
                    "artifact_root": str(
                        artifact_root
                    ),
                    "checked_paths": [
                        str(path)
                        for path in candidates
                    ],
                },
            )

            return None

        except Exception:

            logger.exception(
                "Artifact path resolution failed",
                extra={
                    "artifact_location": str(
                        artifact_location
                    ),
                    "artifact_root": str(
                        self._artifact_root
                    ),
                },
            )

            return None