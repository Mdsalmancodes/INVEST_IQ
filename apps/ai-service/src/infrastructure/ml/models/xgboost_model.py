"""
XGBoost movement-classification model.

INVEST IQ role
--------------

XGBoost is the second tree-based member of the hybrid ensemble.

It consumes the engineered technical-indicator feature matrix and predicts:

    P(BUY / UP)
    P(SELL / DOWN)

The model does NOT produce a direct price forecast.

Its movement probability is consumed by the Hybrid Decision Engine.

Training lifecycle:

    Real OHLCV
        ↓
    FeatureEngineer
        ↓
    supervised feature matrix
        ↓
    chronological train/validation split
        ↓
    XGBClassifier
        ↓
    validation metrics
        ↓
    model artifact

Inference lifecycle:

    Real OHLCV
        ↓
    FeatureEngineer
        ↓
    latest feature row
        ↓
    saved XGBoost model
        ↓
    BUY probability
        ↓
    Hybrid Decision Engine

Important:

- No synthetic OHLCV data is created here.
- No training occurs inside DecisionEngine.
- Feature names are persisted with the artifact.
- Inference validates the feature schema.
- Time-series ordering is preserved.
- Training does NOT shuffle financial observations.
- Class 1 means upward / BUY movement.
- Class 0 means downward / SELL movement.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
from xgboost import XGBClassifier

from src.infrastructure.ml.models.metrics import ClassificationMetrics


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

MINIMUM_HISTORY_DAYS = 20
"""
Minimum raw trading-history requirement for the tree-based model family.

The actual usable feature history can be larger because FeatureEngineer
gates indicators according to their own required lookback windows.
"""

DEFAULT_N_ESTIMATORS = 300
DEFAULT_MAX_DEPTH = 5
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_SUBSAMPLE = 0.90
DEFAULT_COLSAMPLE_BYTREE = 0.90
DEFAULT_MIN_CHILD_WEIGHT = 2
DEFAULT_REG_ALPHA = 0.05
DEFAULT_REG_LAMBDA = 1.0
DEFAULT_RANDOM_STATE = 42


# ============================================================================
# TRAIN RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class XgboostTrainResult:
    """
    Result returned after successful XGBoost training.
    """

    metrics: ClassificationMetrics
    feature_importances: dict[str, float]


# ============================================================================
# XGBOOST MODEL
# ============================================================================


class XgboostModel:
    """
    XGBoost binary movement classifier.

    Class semantics:

        1 -> upward / BUY movement
        0 -> downward / SELL movement

    The primary inference output is the probability of class 1.
    """

    def __init__(
        self,
        n_estimators: int = DEFAULT_N_ESTIMATORS,
        max_depth: int = DEFAULT_MAX_DEPTH,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        subsample: float = DEFAULT_SUBSAMPLE,
        colsample_bytree: float = DEFAULT_COLSAMPLE_BYTREE,
        min_child_weight: int = DEFAULT_MIN_CHILD_WEIGHT,
        reg_alpha: float = DEFAULT_REG_ALPHA,
        reg_lambda: float = DEFAULT_REG_LAMBDA,
        random_state: int = DEFAULT_RANDOM_STATE,
    ) -> None:

        if n_estimators <= 0:
            raise ValueError(
                "n_estimators must be greater than zero"
            )

        if max_depth <= 0:
            raise ValueError(
                "max_depth must be greater than zero"
            )

        if learning_rate <= 0:
            raise ValueError(
                "learning_rate must be greater than zero"
            )

        if not 0.0 < subsample <= 1.0:
            raise ValueError(
                "subsample must be in the range (0, 1]"
            )

        if not 0.0 < colsample_bytree <= 1.0:
            raise ValueError(
                "colsample_bytree must be in the range (0, 1]"
            )

        if min_child_weight <= 0:
            raise ValueError(
                "min_child_weight must be greater than zero"
            )

        if reg_alpha < 0:
            raise ValueError(
                "reg_alpha cannot be negative"
            )

        if reg_lambda < 0:
            raise ValueError(
                "reg_lambda cannot be negative"
            )

        self._model = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            min_child_weight=min_child_weight,
            reg_alpha=reg_alpha,
            reg_lambda=reg_lambda,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=random_state,
            n_jobs=-1,
            tree_method="hist",
        )

        self._feature_names: tuple[str, ...] = ()

        self._is_fitted = False

    # ========================================================================
    # HISTORY CHECK
    # ========================================================================

    @staticmethod
    def has_sufficient_history(
        n_rows: int,
    ) -> bool:
        """
        Check whether the available raw history satisfies the minimum
        tree-model requirement.
        """

        return n_rows >= MINIMUM_HISTORY_DAYS

    # ========================================================================
    # TRAIN
    # ========================================================================

    def train(
        self,
        features: pd.DataFrame,
        labels: pd.Series,
    ) -> XgboostTrainResult:
        """
        Train XGBoost using a chronological train/validation split.

        Financial observations are NOT shuffled.
        """

        # --------------------------------------------------------------------
        # INPUT VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(features, pd.DataFrame):
            raise TypeError(
                "features must be a pandas DataFrame"
            )

        if not isinstance(labels, pd.Series):
            raise TypeError(
                "labels must be a pandas Series"
            )

        if features.empty:
            raise ValueError(
                "XGBoost training requires a non-empty feature dataframe"
            )

        if features.shape[1] == 0:
            raise ValueError(
                "XGBoost training requires at least one feature column"
            )

        if len(features) != len(labels):
            raise ValueError(
                "features and labels must contain the same number of rows"
            )

        if len(features) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"XGBoost training requires at least "
                f"{MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(features)}"
            )

        # --------------------------------------------------------------------
        # FEATURE COLUMN VALIDATION
        # --------------------------------------------------------------------

        if any(
            not isinstance(column, str)
            for column in features.columns
        ):
            raise ValueError(
                "XGBoost feature columns must all be strings"
            )

        if features.columns.duplicated().any():

            duplicated = (
                features.columns[
                    features.columns.duplicated()
                ]
                .tolist()
            )

            raise ValueError(
                f"Duplicate feature columns detected: {duplicated}"
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
                "XGBoost features must be numeric. "
                f"Non-numeric columns: {non_numeric_columns}"
            )

        feature_values = features.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            feature_values
        ).all():

            raise ValueError(
                "XGBoost training features contain "
                "NaN or infinite values."
            )

        # --------------------------------------------------------------------
        # LABEL VALIDATION
        # --------------------------------------------------------------------

        if labels.isna().any():
            raise ValueError(
                "XGBoost training labels contain NaN values."
            )

        labels = labels.astype(int)

        unique_labels = set(
            labels.unique().tolist()
        )

        if not unique_labels.issubset(
            {0, 1}
        ):
            raise ValueError(
                "XGBoost labels must be binary 0/1. "
                f"Received classes: {sorted(unique_labels)}"
            )

        if len(unique_labels) < 2:
            raise ValueError(
                "XGBoost training requires both classes "
                "0 and 1 to be present."
            )

        # --------------------------------------------------------------------
        # STORE FEATURE SCHEMA
        # --------------------------------------------------------------------

        self._feature_names = tuple(
            str(column)
            for column in features.columns
        )

        # --------------------------------------------------------------------
        # CHRONOLOGICAL TRAIN / VALIDATION SPLIT
        # --------------------------------------------------------------------

        split_index = int(
            len(features) * 0.80
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
        ]

        x_validation = features.iloc[
            split_index:
        ]

        y_train = labels.iloc[
            :split_index
        ]

        y_validation = labels.iloc[
            split_index:
        ]

        # --------------------------------------------------------------------
        # TRAINING CLASS VALIDATION
        # --------------------------------------------------------------------

        train_classes = set(
            y_train.unique().tolist()
        )

        if len(train_classes) < 2:

            raise ValueError(
                "XGBoost chronological training split contains "
                "only one class. Increase the training history "
                "or adjust the validation proportion."
            )

        # --------------------------------------------------------------------
        # LOG TRAINING INFORMATION
        # --------------------------------------------------------------------

        print("=" * 78)
        print("🚀 XGBOOST TRAINING")
        print(
            f"📊 TOTAL ROWS: {len(features)}"
        )
        print(
            f"📊 FEATURES: {features.shape[1]}"
        )
        print(
            f"📊 TRAIN ROWS: {len(x_train)}"
        )
        print(
            f"📊 VALIDATION ROWS: {len(x_validation)}"
        )
        print(
            f"📊 TRAIN LABELS: "
            f"{y_train.value_counts().to_dict()}"
        )
        print(
            f"📊 VALIDATION LABELS: "
            f"{y_validation.value_counts().to_dict()}"
        )
        print("=" * 78)

        # --------------------------------------------------------------------
        # FIT
        # --------------------------------------------------------------------

        self._model.fit(
            x_train,
            y_train,
            verbose=False,
        )

        self._is_fitted = True

        # --------------------------------------------------------------------
        # VALIDATION PREDICTIONS
        # --------------------------------------------------------------------

        predictions = self._model.predict(
            x_validation
        )

        # --------------------------------------------------------------------
        # VALIDATION METRICS
        # --------------------------------------------------------------------

        metrics = ClassificationMetrics.compute(
            y_validation.to_numpy(),
            predictions,
        )

        # --------------------------------------------------------------------
        # FEATURE IMPORTANCES
        # --------------------------------------------------------------------

        raw_importances = (
            self._model.feature_importances_
        )

        importances = dict(
            zip(
                self._feature_names,
                (
                    float(value)
                    for value in raw_importances
                ),
                strict=True,
            )
        )

        # --------------------------------------------------------------------
        # NORMALIZE FEATURE IMPORTANCES
        # --------------------------------------------------------------------

        importance_total = sum(
            importances.values()
        )

        if importance_total > 0:

            importances = {
                name: float(
                    value / importance_total
                )
                for name, value
                in importances.items()
            }

        # --------------------------------------------------------------------
        # LOG RESULTS
        # --------------------------------------------------------------------

        print("=" * 78)
        print("✅ XGBOOST TRAINING COMPLETE")
        print(
            f"📊 METRICS: {metrics.as_dict()}"
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

        return XgboostTrainResult(
            metrics=metrics,
            feature_importances=importances,
        )

    # ========================================================================
    # INFERENCE FEATURE VALIDATION
    # ========================================================================

    def _validate_inference_features(
        self,
        features: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate and align inference features against the training schema.
        """

        if not self._is_fitted:

            raise RuntimeError(
                "XgboostModel.train() or load() must be called "
                "before inference."
            )

        if not isinstance(
            features,
            pd.DataFrame,
        ):
            raise TypeError(
                "features must be a pandas DataFrame"
            )

        if features.empty:

            raise ValueError(
                "XGBoost inference features cannot be empty"
            )

        expected = list(
            self._feature_names
        )

        actual = list(
            features.columns
        )

        missing = [
            column
            for column in expected
            if column not in actual
        ]

        unexpected = [
            column
            for column in actual
            if column not in expected
        ]

        if missing:

            raise ValueError(
                "XGBoost inference is missing trained "
                f"feature columns: {missing}"
            )

        if unexpected:

            raise ValueError(
                "XGBoost inference received unexpected "
                f"feature columns: {unexpected}"
            )

        # Always use the exact training feature order.
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
                "XGBoost inference features must be numeric. "
                f"Non-numeric columns: {non_numeric_columns}"
            )

        values = aligned.to_numpy(
            dtype=float
        )

        if not np.isfinite(
            values
        ).all():

            raise ValueError(
                "XGBoost inference features contain "
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
        Return probability of upward / BUY movement.

        Output is in [0, 1].
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

        if len(class_one_positions) == 0:

            raise RuntimeError(
                "XGBoost artifact does not contain "
                "the upward movement class (1)."
            )

        upward_index = int(
            class_one_positions[0]
        )

        return np.asarray(
            probabilities[
                :,
                upward_index,
            ],
            dtype=np.float64,
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

        For this binary classifier:

            sell_probability = 1 - buy_probability
        """

        buy_probability = (
            self.predict_movement(
                features
            )
        )

        sell_probability = (
            1.0 - buy_probability
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
        Return normalized feature importances.
        """

        if not self._is_fitted:

            raise RuntimeError(
                "XgboostModel.train() or load() must be called "
                "before feature_importances()."
            )

        raw_importances = (
            self._model.feature_importances_
        )

        importances = dict(
            zip(
                self._feature_names,
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

        if total > 0:

            importances = {
                name: float(
                    value / total
                )
                for name, value
                in importances.items()
            }

        return importances

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        path: str | Path,
    ) -> None:
        """
        Save the trained XGBoost model and its feature schema.
        """

        if not self._is_fitted:

            raise RuntimeError(
                "XgboostModel.train() or load() must be called "
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
            "model": self._model,
            "feature_names": self._feature_names,
        }

        with artifact_path.open(
            "wb"
        ) as file:

            pickle.dump(
                payload,
                file,
            )

    # ========================================================================
    # LOAD
    # ========================================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
    ) -> XgboostModel:
        """
        Load a previously trained XGBoost artifact.
        """

        artifact_path = Path(
            path
        )

        if not artifact_path.exists():

            raise FileNotFoundError(
                f"XGBoost artifact not found: "
                f"{artifact_path}"
            )

        with artifact_path.open(
            "rb"
        ) as file:

            payload = pickle.load(
                file
            )

        if not isinstance(
            payload,
            dict,
        ):

            raise ValueError(
                "Invalid XGBoost artifact format."
            )

        if "model" not in payload:

            raise ValueError(
                "XGBoost artifact is missing 'model'."
            )

        if "feature_names" not in payload:

            raise ValueError(
                "XGBoost artifact is missing "
                "'feature_names'."
            )

        feature_names = payload[
            "feature_names"
        ]

        if not isinstance(
            feature_names,
            tuple,
        ):

            feature_names = tuple(
                feature_names
            )

        if not feature_names:

            raise ValueError(
                "XGBoost artifact contains "
                "an empty feature schema."
            )

        instance = cls()

        instance._model = payload[
            "model"
        ]

        instance._feature_names = (
            feature_names
        )

        instance._is_fitted = True

        return instance