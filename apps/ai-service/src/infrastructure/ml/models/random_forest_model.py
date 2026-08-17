"""
Random Forest movement-classification model for INVEST IQ.

INVEST IQ role
--------------

Random Forest is one of the tree-based members of the hybrid ensemble.

It consumes the engineered technical-indicator feature matrix and predicts:

    P(UP)
    P(DOWN)

The model does NOT produce a direct price forecast.

Its output is a movement signal consumed by the Hybrid Decision Engine.

Training lifecycle:

    Real OHLCV
        ↓
    FeatureEngineer
        ↓
    supervised feature matrix
        ↓
    chronological train/validation split
        ↓
    validation RandomForestClassifier
        ↓
    validation metrics
        ↓
    NEW final RandomForestClassifier
        ↓
    full-history training
        ↓
    model artifact

Inference lifecycle:

    Real OHLCV
        ↓
    FeatureEngineer
        ↓
    latest feature row
        ↓
    saved Random Forest
        ↓
    upward probability
        ↓
    DecisionEngine

Important architecture rules:

- No synthetic OHLCV data is created here.
- No training happens inside DecisionEngine.
- Feature names are persisted with the model.
- Inference validates the feature schema.
- Time-series ordering is preserved.
- Random shuffling is NEVER used.
- Validation is performed chronologically.
- Validation metrics are calculated BEFORE final refitting.
- The saved model is refitted using 100% of the available training data.
- The model artifact is therefore suitable for serving/inference.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from src.infrastructure.ml.models.metrics import ClassificationMetrics


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

MINIMUM_HISTORY_DAYS = 20
"""
Minimum raw trading-history requirement for the tree-based model family.

The FeatureEngineer may require more history for individual indicators,
such as SMA-200.

The actual usable supervised feature history may therefore be greater
than this value.
"""

DEFAULT_N_ESTIMATORS = 300
DEFAULT_MAX_DEPTH = 8
DEFAULT_MIN_SAMPLES_LEAF = 2
DEFAULT_RANDOM_STATE = 42

DEFAULT_VALIDATION_RATIO = 0.20

ARTIFACT_VERSION = 1
ARTIFACT_TYPE = "invest-iq-random-forest-model"


# ============================================================================
# TRAIN RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class RandomForestTrainResult:
    """
    Result returned after successful Random Forest training.

    metrics:
        Metrics calculated on the chronological validation set.

    feature_importances:
        Feature importances from the FINAL model trained on 100% of the
        available supervised dataset.
    """

    metrics: ClassificationMetrics
    feature_importances: dict[str, float]


# ============================================================================
# RANDOM FOREST MODEL
# ============================================================================


class RandomForestModel:
    """
    Random Forest binary movement classifier.

    Class semantics:

        1 -> upward movement
        0 -> downward / non-upward movement

    Primary inference output:

        probability of class 1.

    Example:

        0.82

    means:

        82% model probability of upward movement.
    """

    def __init__(
        self,
        n_estimators: int = DEFAULT_N_ESTIMATORS,
        max_depth: int | None = DEFAULT_MAX_DEPTH,
        min_samples_leaf: int = DEFAULT_MIN_SAMPLES_LEAF,
        random_state: int = DEFAULT_RANDOM_STATE,
        validation_ratio: float = DEFAULT_VALIDATION_RATIO,
    ) -> None:

        # --------------------------------------------------------------------
        # CONFIGURATION VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            n_estimators,
            int,
        ):
            raise TypeError(
                "n_estimators must be an integer."
            )

        if n_estimators <= 0:
            raise ValueError(
                "n_estimators must be greater than zero."
            )

        if max_depth is not None:

            if not isinstance(
                max_depth,
                int,
            ):
                raise TypeError(
                    "max_depth must be an integer or None."
                )

            if max_depth <= 0:
                raise ValueError(
                    "max_depth must be greater than zero or None."
                )

        if not isinstance(
            min_samples_leaf,
            int,
        ):
            raise TypeError(
                "min_samples_leaf must be an integer."
            )

        if min_samples_leaf <= 0:
            raise ValueError(
                "min_samples_leaf must be greater than zero."
            )

        if not isinstance(
            random_state,
            int,
        ):
            raise TypeError(
                "random_state must be an integer."
            )

        if not (
            0.05
            <= validation_ratio
            < 0.5
        ):
            raise ValueError(
                "validation_ratio must be between "
                "0.05 and 0.49."
            )

        # --------------------------------------------------------------------
        # STORE CONFIGURATION
        # --------------------------------------------------------------------

        self._n_estimators = n_estimators

        self._max_depth = max_depth

        self._min_samples_leaf = (
            min_samples_leaf
        )

        self._random_state = random_state

        self._validation_ratio = (
            float(validation_ratio)
        )

        # --------------------------------------------------------------------
        # CREATE MODEL
        # --------------------------------------------------------------------

        self._model = (
            self._create_classifier()
        )

        # --------------------------------------------------------------------
        # TRAINING FEATURE SCHEMA
        # --------------------------------------------------------------------

        self._feature_names: tuple[str, ...] = ()

        # --------------------------------------------------------------------
        # MODEL STATUS
        # --------------------------------------------------------------------

        self._is_fitted = False

    # ========================================================================
    # MODEL FACTORY
    # ========================================================================

    def _create_classifier(
        self,
    ) -> RandomForestClassifier:
        """
        Create a fresh Random Forest classifier.

        A new classifier is created for the final full-history fit so that
        validation training does not contaminate the serving model lifecycle.
        """

        return RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            min_samples_leaf=self._min_samples_leaf,
            random_state=self._random_state,
            n_jobs=-1,
            class_weight="balanced_subsample",
        )

    # ========================================================================
    # HISTORY CHECK
    # ========================================================================

    @staticmethod
    def has_sufficient_history(
        n_rows: int,
    ) -> bool:
        """
        Check whether the raw market-history length satisfies the minimum
        tree-model requirement.
        """

        if not isinstance(
            n_rows,
            int,
        ):
            return False

        return (
            n_rows >= MINIMUM_HISTORY_DAYS
        )

    # ========================================================================
    # INPUT VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_training_inputs(
        features: pd.DataFrame,
        labels: pd.Series,
    ) -> None:
        """
        Validate the supervised feature matrix and labels.
        """

        # --------------------------------------------------------------------
        # TYPE VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            features,
            pd.DataFrame,
        ):
            raise TypeError(
                "features must be a pandas DataFrame."
            )

        if not isinstance(
            labels,
            pd.Series,
        ):
            raise TypeError(
                "labels must be a pandas Series."
            )

        # --------------------------------------------------------------------
        # EMPTY DATASET
        # --------------------------------------------------------------------

        if features.empty:
            raise ValueError(
                "Random Forest training requires "
                "a non-empty feature dataframe."
            )

        if features.shape[1] == 0:
            raise ValueError(
                "Random Forest training requires "
                "at least one feature column."
            )

        # --------------------------------------------------------------------
        # LENGTH VALIDATION
        # --------------------------------------------------------------------

        if len(features) != len(labels):
            raise ValueError(
                "features and labels must contain "
                "the same number of rows."
            )

        if len(features) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                "Random Forest training requires at least "
                f"{MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(features)}."
            )

        # --------------------------------------------------------------------
        # FEATURE NAME VALIDATION
        # --------------------------------------------------------------------

        if any(
            not isinstance(
                column,
                str,
            )
            for column in features.columns
        ):
            raise ValueError(
                "Random Forest feature columns "
                "must all be strings."
            )

        if features.columns.duplicated().any():

            duplicated = (
                features.columns[
                    features.columns.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                "Duplicate feature columns detected: "
                f"{duplicated}"
            )

        # --------------------------------------------------------------------
        # NUMERIC FEATURE VALIDATION
        # --------------------------------------------------------------------

        non_numeric_columns = [
            column
            for column in features.columns
            if not pd.api.types.is_numeric_dtype(
                features[column]
            )
        ]

        if non_numeric_columns:
            raise ValueError(
                "Random Forest features must be numeric. "
                f"Non-numeric columns: {non_numeric_columns}"
            )

        feature_values = features.to_numpy(
            dtype=np.float64
        )

        if not np.isfinite(
            feature_values
        ).all():
            raise ValueError(
                "Random Forest training features contain "
                "NaN or infinite values."
            )

        # --------------------------------------------------------------------
        # LABEL VALIDATION
        # --------------------------------------------------------------------

        if labels.isna().any():
            raise ValueError(
                "Random Forest training labels "
                "contain NaN values."
            )

        try:
            labels_numeric = labels.astype(
                int
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Random Forest labels must contain "
                "integer-compatible values 0/1."
            ) from exc

        # Ensure conversion did not silently change values.
        original_values = labels.to_numpy()

        converted_values = (
            labels_numeric.to_numpy()
        )

        try:
            if not np.all(
                original_values
                == converted_values
            ):
                raise ValueError(
                    "Random Forest labels must contain "
                    "only integer values 0/1."
                )
        except TypeError as exc:
            raise ValueError(
                "Random Forest labels must contain "
                "integer-compatible values."
            ) from exc

        unique_labels = set(
            labels_numeric.unique().tolist()
        )

        if not unique_labels.issubset(
            {0, 1}
        ):
            raise ValueError(
                "Random Forest labels must be binary 0/1. "
                f"Received classes: "
                f"{sorted(unique_labels)}"
            )

        if len(unique_labels) < 2:
            raise ValueError(
                "Random Forest training requires both classes "
                "0 and 1 to be present."
            )

    # ========================================================================
    # FEATURE IMPORTANCE NORMALIZATION
    # ========================================================================

    @staticmethod
    def _normalize_feature_importances(
        feature_names: tuple[str, ...],
        raw_importances: npt.NDArray[np.float64],
    ) -> dict[str, float]:
        """
        Convert sklearn feature importances into a normalized dictionary.
        """

        importances = dict(
            zip(
                feature_names,
                (
                    float(value)
                    for value in raw_importances
                ),
                strict=True,
            )
        )

        total = sum(
            importances.values()
        )

        if total > 0.0:

            importances = {
                name: float(
                    value / total
                )
                for name, value
                in importances.items()
            }

        return importances

    # ========================================================================
    # TRAIN
    # ========================================================================

    def train(
        self,
        features: pd.DataFrame,
        labels: pd.Series,
    ) -> RandomForestTrainResult:
        """
        Train Random Forest using a chronological validation split.

        Lifecycle:

            1. Validate complete supervised dataset.
            2. Split chronologically into 80/20.
            3. Train temporary validation model on first 80%.
            4. Evaluate on final 20%.
            5. Create a NEW Random Forest.
            6. Train final model on 100% of the data.
            7. Store the final model for serving.
            8. Return validation metrics and final feature importances.

        No random shuffling is performed.
        """

        # --------------------------------------------------------------------
        # VALIDATE INPUTS
        # --------------------------------------------------------------------

        self._validate_training_inputs(
            features,
            labels,
        )

        # --------------------------------------------------------------------
        # NORMALIZE LABELS
        # --------------------------------------------------------------------

        labels = labels.astype(
            int
        )

        # --------------------------------------------------------------------
        # STORE FEATURE SCHEMA
        # --------------------------------------------------------------------

        self._feature_names = tuple(
            str(column)
            for column in features.columns
        )

        # --------------------------------------------------------------------
        # CHRONOLOGICAL SPLIT
        # --------------------------------------------------------------------
        #
        # Earlier observations:
        #     training
        #
        # Later observations:
        #     validation
        #
        # NEVER SHUFFLE FINANCIAL TIME SERIES.
        # --------------------------------------------------------------------

        split_index = int(
            len(features)
            * (
                1.0
                - self._validation_ratio
            )
        )

        split_index = max(
            1,
            min(
                split_index,
                len(features) - 1,
            ),
        )

        x_train = features.iloc[
            :split_index
        ].copy()

        x_validation = features.iloc[
            split_index:
        ].copy()

        y_train = labels.iloc[
            :split_index
        ].copy()

        y_validation = labels.iloc[
            split_index:
        ].copy()

        # --------------------------------------------------------------------
        # TRAINING CLASS VALIDATION
        # --------------------------------------------------------------------

        train_classes = set(
            y_train.unique().tolist()
        )

        if not train_classes.issuperset(
            {0, 1}
        ):
            raise ValueError(
                "Random Forest chronological training split "
                "must contain both classes 0 and 1. "
                f"Training classes: "
                f"{sorted(train_classes)}. "
                "Increase the available history or adjust "
                "the validation ratio."
            )

        # --------------------------------------------------------------------
        # LOG SPLIT INFORMATION
        # --------------------------------------------------------------------

        print("=" * 78)
        print("🌲 RANDOM FOREST VALIDATION TRAINING")
        print("=" * 78)

        print(
            f"📊 TOTAL ROWS       : {len(features)}"
        )

        print(
            f"📊 FEATURES         : {features.shape[1]}"
        )

        print(
            f"📊 TRAIN ROWS      : {len(x_train)}"
        )

        print(
            f"📊 VALIDATION ROWS : {len(x_validation)}"
        )

        print(
            f"📊 TRAIN LABELS    : "
            f"{y_train.value_counts().to_dict()}"
        )

        print(
            f"📊 VALIDATION LABELS: "
            f"{y_validation.value_counts().to_dict()}"
        )

        print("=" * 78)

        # --------------------------------------------------------------------
        # VALIDATION MODEL
        # --------------------------------------------------------------------
        #
        # This model exists ONLY to measure validation performance.
        #
        # It is NOT the final serving model.
        # --------------------------------------------------------------------

        validation_model = (
            self._create_classifier()
        )

        validation_model.fit(
            x_train,
            y_train,
        )

        # --------------------------------------------------------------------
        # VALIDATION PREDICTIONS
        # --------------------------------------------------------------------

        validation_predictions = (
            validation_model.predict(
                x_validation
            )
        )

        # --------------------------------------------------------------------
        # VALIDATION METRICS
        # --------------------------------------------------------------------

        metrics = ClassificationMetrics.compute(
            y_validation.to_numpy(),
            validation_predictions,
        )

        # --------------------------------------------------------------------
        # FINAL FULL-HISTORY MODEL
        # --------------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # The validation model above is discarded.
        #
        # A completely new Random Forest is trained on 100% of the
        # available supervised dataset.
        #
        # This is the model that will be persisted and used by
        # ModelLoader / DecisionEngine.
        # --------------------------------------------------------------------

        print("=" * 78)
        print("🌲 RANDOM FOREST FINAL TRAINING")
        print("=" * 78)

        print(
            "📊 FINAL TRAINING ROWS: "
            f"{len(features)}"
        )

        print(
            "📊 FINAL MODEL DATA: 100% "
            "of available supervised history"
        )

        print("=" * 78)

        final_model = (
            self._create_classifier()
        )

        final_model.fit(
            features,
            labels,
        )

        # --------------------------------------------------------------------
        # STORE FINAL MODEL
        # --------------------------------------------------------------------

        self._model = final_model

        self._is_fitted = True

        # --------------------------------------------------------------------
        # FINAL MODEL FEATURE IMPORTANCES
        # --------------------------------------------------------------------

        importances = (
            self._normalize_feature_importances(
                self._feature_names,
                np.asarray(
                    self._model.feature_importances_,
                    dtype=np.float64,
                ),
            )
        )

        # --------------------------------------------------------------------
        # LOG RESULTS
        # --------------------------------------------------------------------

        print("=" * 78)
        print("✅ RANDOM FOREST TRAINING COMPLETE")
        print("=" * 78)

        print(
            f"📊 VALIDATION METRICS: "
            f"{metrics.as_dict()}"
        )

        print(
            "📊 TOP FEATURES:"
        )

        top_features = sorted(
            importances.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:10]

        for name, importance in top_features:

            print(
                f"   {name}: {importance:.6f}"
            )

        print("=" * 78)

        return RandomForestTrainResult(
            metrics=metrics,
            feature_importances=importances,
        )

    # ========================================================================
    # FEATURE SCHEMA VALIDATION
    # ========================================================================

    def _validate_inference_features(
        self,
        features: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate and reorder the inference feature matrix to exactly match
        the feature schema used during training.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "RandomForestModel.train() or load() must be called "
                "before inference."
            )

        if not isinstance(
            features,
            pd.DataFrame,
        ):
            raise TypeError(
                "features must be a pandas DataFrame."
            )

        if features.empty:
            raise ValueError(
                "Random Forest inference features "
                "cannot be empty."
            )

        if not self._feature_names:
            raise RuntimeError(
                "Random Forest feature schema is unavailable."
            )

        expected = list(
            self._feature_names
        )

        actual = list(
            features.columns
        )

        # --------------------------------------------------------------------
        # MISSING FEATURES
        # --------------------------------------------------------------------

        missing = [
            column
            for column in expected
            if column not in actual
        ]

        if missing:
            raise ValueError(
                "Random Forest inference is missing "
                f"trained feature columns: {missing}"
            )

        # --------------------------------------------------------------------
        # UNEXPECTED FEATURES
        # --------------------------------------------------------------------

        unexpected = [
            column
            for column in actual
            if column not in expected
        ]

        if unexpected:
            raise ValueError(
                "Random Forest inference received unexpected "
                f"feature columns: {unexpected}"
            )

        # --------------------------------------------------------------------
        # EXACT TRAINING ORDER
        # --------------------------------------------------------------------

        aligned = features.loc[
            :,
            expected,
        ].copy()

        # --------------------------------------------------------------------
        # NUMERIC VALIDATION
        # --------------------------------------------------------------------

        non_numeric_columns = [
            column
            for column in aligned.columns
            if not pd.api.types.is_numeric_dtype(
                aligned[column]
            )
        ]

        if non_numeric_columns:
            raise ValueError(
                "Random Forest inference features must be numeric. "
                f"Non-numeric columns: {non_numeric_columns}"
            )

        values = aligned.to_numpy(
            dtype=np.float64
        )

        if not np.isfinite(
            values
        ).all():
            raise ValueError(
                "Random Forest inference features contain "
                "NaN or infinite values."
            )

        return aligned

    # ========================================================================
    # PREDICT MOVEMENT
    # ========================================================================

    def predict_movement(
        self,
        features: pd.DataFrame,
    ) -> npt.NDArray[np.float64]:
        """
        Return the probability of upward movement.

        Output:

            [0.0, 1.0]

        where:

            0.0 -> probability of upward movement is zero
            1.0 -> probability of upward movement is maximum
        """

        aligned_features = (
            self._validate_inference_features(
                features
            )
        )

        probabilities = (
            self._model.predict_proba(
                aligned_features
            )
        )

        classes = self._model.classes_

        class_one_positions = np.where(
            classes == 1
        )[0]

        if len(
            class_one_positions
        ) == 0:
            raise RuntimeError(
                "Random Forest artifact does not contain "
                "the upward movement class (1)."
            )

        upward_index = int(
            class_one_positions[0]
        )

        upward_probabilities = np.asarray(
            probabilities[
                :,
                upward_index,
            ],
            dtype=np.float64,
        )

        if not np.isfinite(
            upward_probabilities
        ).all():
            raise RuntimeError(
                "Random Forest produced NaN or infinite "
                "movement probabilities."
            )

        return np.clip(
            upward_probabilities,
            0.0,
            1.0,
        )

    # ========================================================================
    # BUY / SELL PROBABILITIES
    # ========================================================================

    def predict_buy_sell_probabilities(
        self,
        features: pd.DataFrame,
    ) -> tuple[
        npt.NDArray[np.float64],
        npt.NDArray[np.float64],
    ]:
        """
        Return:

            (
                buy_probability,
                sell_probability,
            )

        Because this is a binary classifier:

            sell_probability = 1 - buy_probability
        """

        buy_probability = (
            self.predict_movement(
                features
            )
        )

        sell_probability = (
            1.0
            - buy_probability
        )

        return (
            buy_probability,
            sell_probability,
        )

    # ========================================================================
    # FEATURE IMPORTANCES
    # ========================================================================

    def feature_importances(
        self,
    ) -> dict[str, float]:
        """
        Return normalized feature importances from the final serving model.

        The values sum approximately to 1.0 when the underlying Random
        Forest exposes non-zero feature importances.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "RandomForestModel.train() or load() must be called "
                "before feature_importances()."
            )

        return (
            self._normalize_feature_importances(
                self._feature_names,
                np.asarray(
                    self._model.feature_importances_,
                    dtype=np.float64,
                ),
            )
        )

    # ========================================================================
    # MODEL STATUS
    # ========================================================================

    @property
    def is_fitted(
        self,
    ) -> bool:
        """
        Return whether the model currently contains a fitted classifier.
        """

        return self._is_fitted

    # ========================================================================
    # FEATURE SCHEMA
    # ========================================================================

    @property
    def feature_names(
        self,
    ) -> tuple[str, ...]:
        """
        Return the feature schema used by the trained model.
        """

        return self._feature_names

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        path: str | Path,
    ) -> None:
        """
        Persist the FINAL trained Random Forest model.

        The artifact contains:

            - artifact type
            - artifact version
            - fitted sklearn model
            - feature schema
            - model configuration

        The artifact is a trusted local model artifact produced by
        TrainModelUseCase and loaded later by ModelLoader.
        """

        if not self._is_fitted:
            raise RuntimeError(
                "RandomForestModel.train() or load() must be called "
                "before save()."
            )

        artifact_path = Path(
            path
        )

        artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "artifact_type": ARTIFACT_TYPE,
            "artifact_version": ARTIFACT_VERSION,
            "model": self._model,
            "feature_names": self._feature_names,
            "configuration": {
                "n_estimators": self._n_estimators,
                "max_depth": self._max_depth,
                "min_samples_leaf": (
                    self._min_samples_leaf
                ),
                "random_state": self._random_state,
                "validation_ratio": (
                    self._validation_ratio
                ),
            },
        }

        with artifact_path.open(
            "wb"
        ) as file:

            pickle.dump(
                payload,
                file,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    # ========================================================================
    # LOAD
    # ========================================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> RandomForestModel:
        """
        Load a previously trained Random Forest artifact.

        Loading does NOT retrain the model.

        The loaded classifier is immediately ready for inference.
        """

        artifact_path = Path(
            path
        )

        # --------------------------------------------------------------------
        # PATH VALIDATION
        # --------------------------------------------------------------------

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Random Forest artifact not found: "
                f"{artifact_path}"
            )

        if not artifact_path.is_file():
            raise ValueError(
                f"Random Forest artifact path is not a file: "
                f"{artifact_path}"
            )

        # --------------------------------------------------------------------
        # LOAD PAYLOAD
        # --------------------------------------------------------------------

        with artifact_path.open(
            "rb"
        ) as file:

            payload = pickle.load(
                file
            )

        # --------------------------------------------------------------------
        # PAYLOAD VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Invalid Random Forest artifact format."
            )

        if payload.get(
            "artifact_type"
        ) != ARTIFACT_TYPE:
            raise ValueError(
                "Artifact is not a valid INVEST IQ "
                "Random Forest model."
            )

        artifact_version = payload.get(
            "artifact_version"
        )

        if artifact_version != ARTIFACT_VERSION:
            raise ValueError(
                "Unsupported Random Forest artifact version: "
                f"{artifact_version}"
            )

        if "model" not in payload:
            raise ValueError(
                "Random Forest artifact is missing 'model'."
            )

        if "feature_names" not in payload:
            raise ValueError(
                "Random Forest artifact is missing "
                "'feature_names'."
            )

        # --------------------------------------------------------------------
        # MODEL VALIDATION
        # --------------------------------------------------------------------

        loaded_model = payload[
            "model"
        ]

        if not isinstance(
            loaded_model,
            RandomForestClassifier,
        ):
            raise ValueError(
                "Random Forest artifact contains an invalid "
                "model object."
            )

        if not hasattr(
            loaded_model,
            "classes_",
        ):
            raise ValueError(
                "Random Forest artifact contains an "
                "unfitted classifier."
            )

        classes = np.asarray(
            loaded_model.classes_
        )

        if 1 not in classes:
            raise ValueError(
                "Random Forest artifact does not contain "
                "the upward movement class (1)."
            )

        # --------------------------------------------------------------------
        # FEATURE SCHEMA VALIDATION
        # --------------------------------------------------------------------

        feature_names = payload[
            "feature_names"
        ]

        if not isinstance(
            feature_names,
            (tuple, list),
        ):
            raise ValueError(
                "Random Forest artifact feature_names "
                "must be a tuple or list."
            )

        feature_names = tuple(
            str(name)
            for name in feature_names
        )

        if not feature_names:
            raise ValueError(
                "Random Forest artifact contains "
                "an empty feature schema."
            )

        if len(
            feature_names
        ) != len(
            set(feature_names)
        ):
            raise ValueError(
                "Random Forest artifact contains "
                "duplicate feature names."
            )

        # --------------------------------------------------------------------
        # CONFIGURATION
        # --------------------------------------------------------------------

        configuration = payload.get(
            "configuration",
            {},
        )

        if not isinstance(
            configuration,
            dict,
        ):
            raise ValueError(
                "Random Forest artifact configuration "
                "must be a dictionary."
            )

        instance = cls(
            n_estimators=int(
                configuration.get(
                    "n_estimators",
                    getattr(
                        loaded_model,
                        "n_estimators",
                        DEFAULT_N_ESTIMATORS,
                    ),
                )
            ),
            max_depth=configuration.get(
                "max_depth",
                getattr(
                    loaded_model,
                    "max_depth",
                    DEFAULT_MAX_DEPTH,
                ),
            ),
            min_samples_leaf=int(
                configuration.get(
                    "min_samples_leaf",
                    getattr(
                        loaded_model,
                        "min_samples_leaf",
                        DEFAULT_MIN_SAMPLES_LEAF,
                    ),
                )
            ),
            random_state=int(
                configuration.get(
                    "random_state",
                    getattr(
                        loaded_model,
                        "random_state",
                        DEFAULT_RANDOM_STATE,
                    ),
                )
            ),
            validation_ratio=float(
                configuration.get(
                    "validation_ratio",
                    DEFAULT_VALIDATION_RATIO,
                )
            ),
        )

        # --------------------------------------------------------------------
        # RESTORE FITTED MODEL
        # --------------------------------------------------------------------

        instance._model = (
            loaded_model
        )

        instance._feature_names = (
            feature_names
        )

        instance._is_fitted = True

        return instance