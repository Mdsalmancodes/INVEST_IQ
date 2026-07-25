"""Random Forest movement-classification model — Document 4 §10.2's
gradient/tree-based ensemble member, "trained on the full engineered
feature set... captures fundamental/sentiment interactions the sequence
models can't see directly." Per the founder's Phase 7 instruction: predict
upward/downward movement + feature importance.

Per Document 4 §10.1a: tree-based models minimum history = 20 trading days
("needs enough rows to have engineered features at all").
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

MINIMUM_HISTORY_DAYS = 20
"""Per Document 4 §10.1a's tree-based-model row: '20 trading days'
minimum ('needs enough rows to have engineered features at all')."""


@dataclass(frozen=True, slots=True)
class RandomForestTrainResult:
    metrics: ClassificationMetrics
    feature_importances: dict[str, float]


class RandomForestModel:
    """Wraps `sklearn.ensemble.RandomForestClassifier` for binary
    up/down price-movement classification over the engineered feature
    matrix (not just close price, unlike LSTM/ARIMA/Prophet) — Document 4
    §10.2 step 2's explicit division of labor between sequence models and
    tree-based models."""

    def __init__(self, n_estimators: int = 100, max_depth: int | None = 6) -> None:
        self._model = RandomForestClassifier(
            n_estimators=n_estimators, max_depth=max_depth, random_state=42
        )
        self._feature_names: tuple[str, ...] = ()
        self._is_fitted = False

    @staticmethod
    def has_sufficient_history(n_rows: int) -> bool:
        return n_rows >= MINIMUM_HISTORY_DAYS

    def train(self, features: pd.DataFrame, labels: pd.Series) -> RandomForestTrainResult:
        if len(features) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"Random Forest training requires at least {MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(features)}"
            )
        if features.empty or features.shape[1] == 0:
            raise ValueError("Random Forest training requires at least one feature column")

        self._feature_names = tuple(features.columns)
        split = max(1, int(len(features) * 0.8))
        x_train, x_val = features.iloc[:split], features.iloc[split:]
        y_train, y_val = labels.iloc[:split], labels.iloc[split:]

        if len(x_val) == 0:
            x_val, y_val = x_train, y_train

        self._model.fit(x_train, y_train)
        self._is_fitted = True

        predictions = self._model.predict(x_val)
        metrics = ClassificationMetrics.compute(y_val.to_numpy(), predictions)

        importances = dict(zip(self._feature_names, self._model.feature_importances_, strict=True))
        return RandomForestTrainResult(
            metrics=metrics, feature_importances={k: float(v) for k, v in importances.items()}
        )

    def predict_movement(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Returns the predicted probability of UPWARD movement (class 1)
        for each row in `features` — Document 4's 'Predict Upward/
        Downward Movement' requirement, expressed as a probability rather
        than a bare label so the Decision Engine can weight it against
        other ensemble members' confidence."""
        if not self._is_fitted:
            raise RuntimeError("RandomForestModel.train() must be called before predict_movement()")
        probabilities = self._model.predict_proba(features)
        # predict_proba's column order matches self._model.classes_ — the
        # "upward" class is 1, per classification_labels_from_returns().
        upward_index = int(np.where(self._model.classes_ == 1)[0][0])
        return np.asarray(probabilities[:, upward_index], dtype=np.float64)

    def feature_importances(self) -> dict[str, float]:
        if not self._is_fitted:
            raise RuntimeError(
                "RandomForestModel.train() must be called before feature_importances()"
            )
        return dict(
            zip(
                self._feature_names,
                (float(v) for v in self._model.feature_importances_),
                strict=True,
            )
        )

    def save(self, path: str | Path) -> None:
        if not self._is_fitted:
            raise RuntimeError("RandomForestModel.train() must be called before save()")
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("wb") as f:
            pickle.dump({"model": self._model, "feature_names": self._feature_names}, f)

    @classmethod
    def load(cls, path: str | Path) -> RandomForestModel:
        with Path(path).open("rb") as f:
            payload = pickle.load(f)  # noqa: S301 — trusted local artifact, matches ArimaModel.load's contract
        instance = cls()
        instance._model = payload["model"]
        instance._feature_names = payload["feature_names"]
        instance._is_fitted = True
        return instance
