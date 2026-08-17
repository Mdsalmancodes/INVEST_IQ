"""
TrainModelUseCase and RetrainModelUseCase.

INVEST IQ model-training lifecycle:

    Real OHLCV market data
            ↓
    Model-specific preprocessing
            ↓
    Train model
            ↓
    Validate model
            ↓
    Save artifact
            ↓
    Register ModelVersion
            ↓
    ModelLoader loads artifact for inference

Supported trainable model families:

    LSTM
    ARIMA
    Prophet
    Random Forest
    XGBoost

FinBERT is pretrained and is NOT fine-tuned by this use case.

Architecture rules:

1. Training happens offline through this use case.
2. DecisionEngine performs inference only.
3. Training uses repository-provided OHLCV data.
4. Random Forest/XGBoost use FeatureEngineer.
5. Random Forest/XGBoost use binary movement classification:

       1 = future close > current close
       0 = future close <= current close

6. Training does not fabricate OHLCV values.
7. Failed retraining never retires the currently active model.
8. Model artifacts are stored below the configured artifact root.
9. ModelVersion records symbol, artifact location and validation metrics.
10. Previous active model remains active until replacement training
    completes successfully.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.domain.ml.entities import ModelVersion
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import (
    MarketDataRepository,
    ModelRegistryRepository,
)
from src.domain.ml.value_objects import (
    ModelFamily,
    ModelVersionId,
)

from src.infrastructure.ml.features.engineer import FeatureEngineer
from src.infrastructure.ml.models.arima_model import ArimaModel
from src.infrastructure.ml.models.lstm_model import LstmModel
from src.infrastructure.ml.models.prophet_model import (
    ProphetModel,
)
from src.infrastructure.ml.models.random_forest_model import (
    RandomForestModel,
)
from src.infrastructure.ml.models.xgboost_model import (
    XgboostModel,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

_ARTIFACT_EXTENSIONS: dict[ModelFamily, str] = {
    "lstm": "pt",
    "arima": "pkl",
    "prophet": "pkl",
    "random_forest": "pkl",
    "xgboost": "pkl",
    "finbert": "none",
}


_TRAINABLE_FAMILIES: tuple[ModelFamily, ...] = (
    "lstm",
    "arima",
    "prophet",
    "random_forest",
    "xgboost",
)


# ============================================================================
# COMMAND
# ============================================================================


@dataclass(frozen=True, slots=True)
class TrainModelCommand:
    """
    Command for training one model family for one stock symbol.
    """

    family: ModelFamily
    symbol: str
    lookback_days: int = 400


# ============================================================================
# RESULT
# ============================================================================
@dataclass(frozen=True, slots=True)
class TrainModelResult:
    """
    Result returned after successful model training.

    The commonly accessed application-level fields are exposed directly
    so callers do not have to navigate through ModelVersion.

    Available fields:

        result.symbol
        result.family
        result.status
        result.version_tag
        result.model_version_id
        result.artifact_location
        result.validation_metrics
        result.model_version
    """

    symbol: str
    family: ModelFamily
    status: str
    version_tag: str
    model_version_id: ModelVersionId
    artifact_location: str
    validation_metrics: dict[str, float]
    model_version: ModelVersion



# ============================================================================
# TRAIN MODEL USE CASE
# ============================================================================


class TrainModelUseCase:
    """
    Train one model family using historical OHLCV data.

    Training is separated from inference.

    Lifecycle:

        MarketDataRepository
                ↓
              OHLCV
                ↓
        model-specific training
                ↓
             artifact
                ↓
          ModelVersion
                ↓
        ModelRegistryRepository
    """

    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        model_registry_repository: ModelRegistryRepository,
        artifact_storage_root: str | Path,
    ) -> None:

        self._market_data_repository = (
            market_data_repository
        )

        self._model_registry_repository = (
            model_registry_repository
        )

        self._artifact_root = Path(
            artifact_storage_root
        )

    # ========================================================================
    # EXECUTE
    # ========================================================================

    async def execute(
        self,
        command: TrainModelCommand,
    ) -> TrainModelResult:

        # --------------------------------------------------------------------
        # NORMALIZE SYMBOL
        # --------------------------------------------------------------------

        symbol = (
            command.symbol
            .upper()
            .strip()
        )

        if not symbol:
            raise ValueError(
                "Training symbol must not be empty."
            )

        # --------------------------------------------------------------------
        # VALIDATE LOOKBACK
        # --------------------------------------------------------------------

        if command.lookback_days <= 0:
            raise ValueError(
                "lookback_days must be greater than zero."
            )

        # --------------------------------------------------------------------
        # VALIDATE MODEL FAMILY
        # --------------------------------------------------------------------

        if command.family not in _TRAINABLE_FAMILIES:

            if command.family == "finbert":
                raise ValueError(
                    "FinBERT is a pretrained model and is "
                    "inference-only; it must not be trained "
                    "through TrainModelUseCase."
                )

            raise ValueError(
                "Unsupported trainable model family: "
                f"{command.family!r}"
            )

        # --------------------------------------------------------------------
        # DATE RANGE
        # --------------------------------------------------------------------

        end = date.today()

        start = (
            end
            - timedelta(
                days=command.lookback_days
            )
        )

        # --------------------------------------------------------------------
        # LOGGING
        # --------------------------------------------------------------------

        print("=" * 78)
        print("INVEST IQ MODEL TRAINING")
        print("=" * 78)

        print(
            f"📌 SYMBOL        : {symbol}"
        )

        print(
            f"📌 MODEL FAMILY  : {command.family}"
        )

        print(
            f"📌 LOOKBACK DAYS : {command.lookback_days}"
        )

        print(
            f"📌 START DATE    : {start}"
        )

        print(
            f"📌 END DATE      : {end}"
        )

        print()
        print(
            "📡 Fetching REAL OHLCV market data..."
        )

        # --------------------------------------------------------------------
        # FETCH MARKET DATA
        # --------------------------------------------------------------------

        bars = await (
            self._market_data_repository
            .get_ohlcv_bars(
                symbol,
                start,
                end,
            )
        )

        if not bars:
            raise InsufficientDataError(
                f"No OHLCV history available for "
                f"{symbol!r}; cannot train "
                f"{command.family!r}."
            )

        print(
            f"✅ Received {len(bars)} real OHLCV bars."
        )

        # --------------------------------------------------------------------
        # BUILD CANONICAL OHLCV DATAFRAME
        # --------------------------------------------------------------------

        ohlcv = self._build_ohlcv_dataframe(
            bars
        )

        if ohlcv.empty:
            raise InsufficientDataError(
                f"OHLCV history for {symbol!r} "
                "is empty after normalization."
            )

        # --------------------------------------------------------------------
        # VALIDATE OHLCV
        # --------------------------------------------------------------------

        self._validate_ohlcv(
            ohlcv=ohlcv,
            symbol=symbol,
        )

        print(
            "✅ OHLCV validation passed."
        )

        print(
            f"📊 Training bars: {len(ohlcv)}"
        )

        print(
            "📅 Training range: "
            f"{ohlcv.index[0]} → "
            f"{ohlcv.index[-1]}"
        )

        # --------------------------------------------------------------------
        # CREATE VERSION TAG
        # --------------------------------------------------------------------

        version_tag = (
            datetime.now(UTC)
            .strftime(
                "%Y%m%dT%H%M%S%fZ"
            )
        )

        # --------------------------------------------------------------------
        # ARTIFACT EXTENSION
        # --------------------------------------------------------------------

        extension = _ARTIFACT_EXTENSIONS[
            command.family
        ]

        # --------------------------------------------------------------------
        # ARTIFACT PATH
        # --------------------------------------------------------------------

        artifact_path = (
            self._artifact_root
            / command.family
            / symbol
            / f"{version_tag}.{extension}"
        )

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        print()
        print(
            "📦 Artifact path:"
        )

        print(
            f"   {artifact_path}"
        )

        # --------------------------------------------------------------------
        # TRAIN
        # --------------------------------------------------------------------

        print()
        print(
            "🧠 Starting model training..."
        )

        validation_metrics = await (
            asyncio.to_thread(
                self._train_and_save,
                command,
                ohlcv,
                artifact_path,
            )
        )

        # --------------------------------------------------------------------
        # VERIFY ARTIFACT
        # --------------------------------------------------------------------

        if not artifact_path.exists():
            raise RuntimeError(
                "Training completed but model artifact "
                f"was not created: {artifact_path}"
            )

        if not artifact_path.is_file():
            raise RuntimeError(
                "Model artifact path exists but is not "
                f"a file: {artifact_path}"
            )

        if artifact_path.stat().st_size <= 0:
            raise RuntimeError(
                "Model artifact was created but is empty: "
                f"{artifact_path}"
            )

        print()
        print(
            "✅ Model artifact created successfully."
        )

        print(
            f"📦 Size: "
            f"{artifact_path.stat().st_size:,} bytes"
        )

        # --------------------------------------------------------------------
        # TRAINING DATE RANGE
        # --------------------------------------------------------------------

        training_start = (
            ohlcv.index[0]
            .to_pydatetime()
        )

        training_end = (
            ohlcv.index[-1]
            .to_pydatetime()
        )

        # --------------------------------------------------------------------
        # CREATE MODEL VERSION
        # --------------------------------------------------------------------

        model_version = (
            ModelVersion.create(
                family=command.family,
                symbol=symbol,
                version_tag=version_tag,
                training_data_range_start=(
                    training_start
                ),
                training_data_range_end=(
                    training_end
                ),
                validation_metrics=(
                    validation_metrics
                ),
                artifact_location=str(
                    artifact_path
                ),
            )
        )

        # --------------------------------------------------------------------
        # REGISTER MODEL VERSION
        # --------------------------------------------------------------------

        await (
            self._model_registry_repository
            .save(
                model_version
            )
        )

        # --------------------------------------------------------------------
        # SUCCESS
        # --------------------------------------------------------------------

        print()
        print("=" * 78)
        print(
            "✅ MODEL TRAINING COMPLETE"
        )
        print("=" * 78)

        print(
            f"📌 SYMBOL       : {symbol}"
        )

        print(
            f"📌 FAMILY       : {command.family}"
        )

        print(
            f"📌 VERSION      : {version_tag}"
        )

        print(
            f"📌 STATUS       : "
            f"{model_version.status}"
        )

        print(
            f"📌 ARTIFACT     : "
            f"{artifact_path}"
        )

        print(
            f"📌 METRICS      : "
            f"{validation_metrics}"
        )

        print("=" * 78)

        # --------------------------------------------------------------------
        # RETURN COMPLETE APPLICATION RESULT
        # --------------------------------------------------------------------

        return TrainModelResult(
            symbol=symbol,
            family=command.family,
            status=model_version.status,
            version_tag=model_version.version_tag,
            model_version_id=model_version.id,
            artifact_location=model_version.artifact_location,
            validation_metrics=validation_metrics,
            model_version=model_version,
        )

    # ========================================================================
    # BUILD OHLCV DATAFRAME
    # ========================================================================

    @staticmethod
    def _build_ohlcv_dataframe(
        bars: Any,
    ) -> pd.DataFrame:
        """
        Convert repository OHLCV objects into a canonical DataFrame.

        No market data is fabricated.
        """

        rows: list[dict[str, object]] = []

        for bar in bars:

            rows.append(
                {
                    "bar_time": bar.bar_time,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
            )

        if not rows:

            return pd.DataFrame(
                columns=[
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            )

        dataframe = pd.DataFrame(
            rows
        )

        # --------------------------------------------------------------------
        # DATETIME
        # --------------------------------------------------------------------

        dataframe["bar_time"] = (
            pd.to_datetime(
                dataframe["bar_time"],
                errors="coerce",
            )
        )

        dataframe = (
            dataframe
            .dropna(
                subset=["bar_time"]
            )
        )

        # --------------------------------------------------------------------
        # SORT CHRONOLOGICALLY
        # --------------------------------------------------------------------

        dataframe = (
            dataframe
            .sort_values(
                "bar_time"
            )
        )

        # --------------------------------------------------------------------
        # REMOVE DUPLICATE BARS
        # --------------------------------------------------------------------

        dataframe = (
            dataframe
            .drop_duplicates(
                subset=["bar_time"],
                keep="last",
            )
        )

        # --------------------------------------------------------------------
        # SET INDEX
        # --------------------------------------------------------------------

        dataframe = (
            dataframe
            .set_index(
                "bar_time"
            )
        )

        return dataframe[
            [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]

    # ========================================================================
    # VALIDATE OHLCV
    # ========================================================================

    @staticmethod
    def _validate_ohlcv(
        ohlcv: pd.DataFrame,
        symbol: str,
    ) -> None:
        """
        Validate canonical OHLCV data before training.
        """

        # --------------------------------------------------------------------
        # REQUIRED COLUMNS
        # --------------------------------------------------------------------

        required_columns = {
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        missing_columns = (
            required_columns
            - set(ohlcv.columns)
        )

        if missing_columns:

            raise ValueError(
                f"OHLCV data for {symbol} "
                "is missing columns: "
                f"{sorted(missing_columns)}"
            )

        # --------------------------------------------------------------------
        # EMPTY
        # --------------------------------------------------------------------

        if ohlcv.empty:

            raise InsufficientDataError(
                f"No usable OHLCV rows available "
                f"for {symbol}."
            )

        # --------------------------------------------------------------------
        # NUMERIC VALIDATION
        # --------------------------------------------------------------------

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for column in numeric_columns:

            ohlcv[column] = (
                pd.to_numeric(
                    ohlcv[column],
                    errors="coerce",
                )
            )

        # --------------------------------------------------------------------
        # NaN VALIDATION
        # --------------------------------------------------------------------

        if (
            ohlcv[
                numeric_columns
            ]
            .isna()
            .any()
            .any()
        ):

            invalid_columns = [
                column
                for column in numeric_columns
                if ohlcv[column]
                .isna()
                .any()
            ]

            raise ValueError(
                f"Invalid numeric OHLCV values "
                f"for {symbol}: "
                f"{invalid_columns}"
            )

        # --------------------------------------------------------------------
        # POSITIVE PRICES
        # --------------------------------------------------------------------

        price_columns = [
            "open",
            "high",
            "low",
            "close",
        ]

        if (
            ohlcv[
                price_columns
            ]
            <= 0
        ).any().any():

            raise ValueError(
                f"OHLC prices for {symbol} "
                "must be greater than zero."
            )

        # --------------------------------------------------------------------
        # VOLUME
        # --------------------------------------------------------------------

        if (
            ohlcv["volume"] < 0
        ).any():

            raise ValueError(
                f"Volume values for {symbol} "
                "cannot be negative."
            )

        # --------------------------------------------------------------------
        # HIGH
        # --------------------------------------------------------------------

        invalid_high = (
            ohlcv["high"]
            < ohlcv[
                [
                    "open",
                    "close",
                ]
            ].max(axis=1)
        )

        if invalid_high.any():

            raise ValueError(
                f"Invalid OHLC data for {symbol}: "
                "high is below open or close."
            )

        # --------------------------------------------------------------------
        # LOW
        # --------------------------------------------------------------------

        invalid_low = (
            ohlcv["low"]
            > ohlcv[
                [
                    "open",
                    "close",
                ]
            ].min(axis=1)
        )

        if invalid_low.any():

            raise ValueError(
                f"Invalid OHLC data for {symbol}: "
                "low is above open or close."
            )

    # ========================================================================
    # TRAIN AND SAVE
    # ========================================================================

    def _train_and_save(
        self,
        command: TrainModelCommand,
        ohlcv: pd.DataFrame,
        artifact_path: Path,
    ) -> dict[str, float]:
        """
        Perform synchronous training and artifact persistence.

        This method is called through asyncio.to_thread().
        """

        family = command.family

        # ====================================================================
        # LSTM
        # ====================================================================

        if family == "lstm":

            print()
            print(
                "🟢 LSTM TRAIN START"
            )

            close = (
                ohlcv["close"]
                .to_numpy(
                    dtype=float
                )
            )

            model = LstmModel()

            result = model.train(
                close
            )

            model.save(
                artifact_path
            )

            print(
                "🟢 LSTM TRAIN COMPLETE"
            )

            return (
                result.metrics.as_dict()
            )

        # ====================================================================
        # ARIMA
        # ====================================================================

        if family == "arima":

            print()
            print(
                "🟣 ARIMA TRAIN START"
            )

            close = (
                ohlcv["close"]
                .to_numpy(
                    dtype=float
                )
            )

            model = ArimaModel()

            result = model.train(
                close
            )

            model.save(
                artifact_path
            )

            print(
                "🟣 ARIMA TRAIN COMPLETE"
            )

            return (
                result.metrics.as_dict()
            )

        # ====================================================================
        # PROPHET
        # ====================================================================

        if family == "prophet":

            print()
            print(
                "🔵 PROPHET TRAIN START"
            )

            dates = (
                ohlcv.index
                .to_numpy()
            )

            close = (
                ohlcv["close"]
                .to_numpy(
                    dtype=float
                )
            )

            model = ProphetModel()

            result = model.train(
                dates,
                close,
            )

            model.save(
                artifact_path
            )

            print(
                "🔵 PROPHET TRAIN COMPLETE"
            )

            return (
                result.metrics.as_dict()
            )

        # ====================================================================
        # RANDOM FOREST / XGBOOST
        # ====================================================================

        if family in (
            "random_forest",
            "xgboost",
        ):

            print()
            print(
                f"🌳 {family.upper()} TRAIN START"
            )

            # ----------------------------------------------------------------
            # FEATURE ENGINEERING
            # ----------------------------------------------------------------

            engineer = FeatureEngineer()

            feature_matrix = (
                engineer.build(
                    ohlcv
                )
            )

            if feature_matrix.raw.empty:

                raise InsufficientDataError(
                    f"Feature engineering produced "
                    f"no usable features for "
                    f"{command.symbol!r}."
                )

            print(
                f"📊 RAW FEATURE SHAPE: "
                f"{feature_matrix.raw.shape}"
            )

            print(
                f"📊 FEATURES: "
                f"{list(feature_matrix.raw.columns)}"
            )

            print(
                f"📊 OMITTED FEATURES: "
                f"{list(feature_matrix.omitted_columns)}"
            )

            # ----------------------------------------------------------------
            # CLASSIFICATION DATASET
            # ----------------------------------------------------------------

            features, labels = (
                FeatureEngineer
                .to_classification_dataset(
                    raw_features=(
                        feature_matrix.raw
                    ),
                    close=(
                        ohlcv["close"]
                    ),
                    horizon_days=1,
                )
            )

            if features.empty:

                raise InsufficientDataError(
                    f"No classification training "
                    f"rows available for "
                    f"{command.symbol!r}."
                )

            if labels.empty:

                raise InsufficientDataError(
                    f"No classification labels "
                    f"available for "
                    f"{command.symbol!r}."
                )

            # ----------------------------------------------------------------
            # LABEL TYPE
            # ----------------------------------------------------------------

            labels = (
                labels
                .astype(int)
            )

            # ----------------------------------------------------------------
            # BINARY CLASS VALIDATION
            # ----------------------------------------------------------------

            unique_labels = sorted(
                labels
                .unique()
                .tolist()
            )

            if unique_labels != [
                0,
                1,
            ]:

                raise InsufficientDataError(
                    f"{family} training for "
                    f"{command.symbol!r} requires "
                    "both binary classes 0 and 1. "
                    f"Found: {unique_labels}"
                )

            # ----------------------------------------------------------------
            # LOGGING
            # ----------------------------------------------------------------

            print(
                f"📊 CLASSIFICATION FEATURES: "
                f"{features.shape}"
            )

            print(
                f"📊 CLASSIFICATION LABELS: "
                f"{labels.shape}"
            )

            label_distribution = (
                labels
                .value_counts()
                .sort_index()
                .to_dict()
            )

            print(
                "📊 LABEL DISTRIBUTION: "
                f"{label_distribution}"
            )

            print(
                "📊 LABEL MEANING:"
            )

            print(
                "   1 = future close > current close"
            )

            print(
                "   0 = future close <= current close"
            )

            # =================================================================
            # RANDOM FOREST
            # =================================================================

            if family == "random_forest":

                print()
                print(
                    "🌲 Training Random Forest..."
                )

                model = (
                    RandomForestModel()
                )

                result = model.train(
                    features,
                    labels,
                )

                model.save(
                    artifact_path
                )

                print(
                    "🟡 RANDOM FOREST "
                    "TRAIN COMPLETE"
                )

                print(
                    f"📈 METRICS: "
                    f"{result.metrics.as_dict()}"
                )

                return (
                    result.metrics.as_dict()
                )

            # =================================================================
            # XGBOOST
            # =================================================================

            print()
            print(
                "⚡ Training XGBoost..."
            )

            model = (
                XgboostModel()
            )

            result = model.train(
                features,
                labels,
            )

            model.save(
                artifact_path
            )

            print(
                "🔶 XGBOOST TRAIN COMPLETE"
            )

            print(
                f"📈 METRICS: "
                f"{result.metrics.as_dict()}"
            )

            return (
                result.metrics.as_dict()
            )

        # ====================================================================
        # SAFETY NET
        # ====================================================================

        raise ValueError(
            "Unsupported trainable model family: "
            f"{family!r}"
        )


# ============================================================================
# RETRAIN MODEL USE CASE
# ============================================================================


class RetrainModelUseCase:
    """
    Safely retrain one model family for one symbol.

    Critical lifecycle:

        OLD ACTIVE MODEL
                ↓
        train replacement
                ↓
        validate replacement
                ↓
        save artifact
                ↓
        register replacement
                ↓
        retire OLD MODEL

    If replacement training fails:

        OLD ACTIVE MODEL
                ↓
              REMAINS ACTIVE
    """

    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        model_registry_repository: ModelRegistryRepository,
        artifact_storage_root: str | Path,
    ) -> None:

        self._train_use_case = (
            TrainModelUseCase(
                market_data_repository=(
                    market_data_repository
                ),
                model_registry_repository=(
                    model_registry_repository
                ),
                artifact_storage_root=(
                    artifact_storage_root
                ),
            )
        )

        self._model_registry_repository = (
            model_registry_repository
        )

    # ========================================================================
    # FIND PREVIOUS ACTIVE MODEL
    # ========================================================================

    async def _get_previous_active(
        self,
        family: ModelFamily,
        symbol: str,
    ) -> ModelVersion | None:
        """
        Find the active model for a specific family and symbol.

        Preferred repository method:

            get_active_for_family_and_symbol()

        Compatibility fallback:

            get_active_for_family()

        The fallback protects compatibility with older test fakes and
        repository implementations.
        """

        repository = (
            self._model_registry_repository
        )

        # --------------------------------------------------------------------
        # PREFERRED SYMBOL-AWARE METHOD
        # --------------------------------------------------------------------

        get_symbol_aware = getattr(
            repository,
            "get_active_for_family_and_symbol",
            None,
        )

        if callable(get_symbol_aware):

            result = await get_symbol_aware(
                family,
                symbol,
            )

            return result

        # --------------------------------------------------------------------
        # LEGACY FAMILY-ONLY METHOD
        # --------------------------------------------------------------------

        get_family_only = getattr(
            repository,
            "get_active_for_family",
            None,
        )

        if not callable(get_family_only):

            raise AttributeError(
                "ModelRegistryRepository must provide "
                "get_active_for_family_and_symbol() "
                "or get_active_for_family()."
            )

        result = await get_family_only(
            family
        )

        if result is None:
            return None

        result_symbol = (
            getattr(
                result,
                "symbol",
                "",
            )
            or ""
        )

        if (
            result_symbol.upper()
            != symbol.upper()
        ):
            return None

        return result

    # ========================================================================
    # EXECUTE
    # ========================================================================

    async def execute(
        self,
        command: TrainModelCommand,
    ) -> TrainModelResult:

        # --------------------------------------------------------------------
        # NORMALIZE SYMBOL
        # --------------------------------------------------------------------

        symbol = (
            command.symbol
            .upper()
            .strip()
        )

        if not symbol:

            raise ValueError(
                "Training symbol must not be empty."
            )

        # --------------------------------------------------------------------
        # VALIDATE LOOKBACK
        # --------------------------------------------------------------------

        if command.lookback_days <= 0:

            raise ValueError(
                "lookback_days must be greater than zero."
            )

        # --------------------------------------------------------------------
        # VALIDATE FAMILY
        # --------------------------------------------------------------------

        if command.family == "finbert":

            raise ValueError(
                "FinBERT is a pretrained model and is "
                "inference-only; it must not be retrained "
                "through RetrainModelUseCase."
            )

        if command.family not in _TRAINABLE_FAMILIES:

            raise ValueError(
                "Unsupported trainable model family: "
                f"{command.family!r}"
            )

        # --------------------------------------------------------------------
        # FIND CURRENT ACTIVE MODEL
        # --------------------------------------------------------------------

        previous_active = await (
            self._get_previous_active(
                family=command.family,
                symbol=symbol,
            )
        )

        if previous_active is not None:

            print()
            print(
                "♻️ Existing active model found."
            )

            print(
                f"   Family : "
                f"{previous_active.family}"
            )

            print(
                f"   Symbol : "
                f"{previous_active.symbol}"
            )

            print(
                f"   Version: "
                f"{previous_active.version_tag}"
            )

        else:

            print()
            print(
                "ℹ️ No previous active model found "
                f"for {command.family}/{symbol}."
            )

        # --------------------------------------------------------------------
        # TRAIN REPLACEMENT FIRST
        # --------------------------------------------------------------------
        #
        # DO NOT RETIRE previous_active before this call.
        #
        # If this fails, previous_active stays untouched.
        # --------------------------------------------------------------------

        result = await (
            self._train_use_case.execute(
                TrainModelCommand(
                    family=command.family,
                    symbol=symbol,
                    lookback_days=(
                        command.lookback_days
                    ),
                )
            )
        )

        # --------------------------------------------------------------------
        # NEW MODEL SUCCESSFULLY REGISTERED
        # --------------------------------------------------------------------

        new_model_version = (
            result.model_version
        )

        # --------------------------------------------------------------------
        # RETIRE PREVIOUS ACTIVE MODEL
        # --------------------------------------------------------------------

        if previous_active is not None:

            previous_version_tag = (
                previous_active.version_tag
            )

            previous_active.retire()

            await (
                self._model_registry_repository
                .save(
                    previous_active
                )
            )

            print()
            print(
                "♻️ Previous model retired:"
            )

            print(
                f"   {previous_version_tag}"
            )

        # --------------------------------------------------------------------
        # SUCCESS
        # --------------------------------------------------------------------

        print()
        print("=" * 78)
        print(
            "♻️ MODEL RETRAIN COMPLETE"
        )
        print("=" * 78)

        print(
            f"📌 SYMBOL       : {symbol}"
        )

        print(
            f"📌 FAMILY       : "
            f"{command.family}"
        )

        print(
            f"📌 NEW VERSION  : "
            f"{new_model_version.version_tag}"
        )

        print(
            f"📌 STATUS       : "
            f"{new_model_version.status}"
        )

        print(
            f"📌 ARTIFACT     : "
            f"{new_model_version.artifact_location}"
        )

        print(
            f"📌 METRICS      : "
            f"{result.validation_metrics}"
        )

        print("=" * 78)

        return result