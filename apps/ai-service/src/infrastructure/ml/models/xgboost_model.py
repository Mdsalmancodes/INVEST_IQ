"""XGBoost movement-classification model — Document 4 §10.2's other
gradient-boosted-tree ensemble member alongside Random Forest, trained on
the same engineered feature set. Per the founder's Phase 7 instruction:
predict buy probability, sell probability, movement classification.

Per Document 4 §10.1a: 'XGBoost/LightGBM/CatBoost' minimum history = 20
trading days (same tree-based-model row as Random Forest).

This module intentionally mirrors random_forest_model.py's structure
closely — both are tree-based models consuming the same FeatureEngineer
output via the same train(features, labels) -> TrainResult /
predict_movement() / feature_importances() / save() / load() interface,
differing mainly in the underlying estimator class and hyperparameters,
matching how ArimaModel and ProphetModel similarly mirror each other's
statistical-baseline interface.
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

MINIMUM_HISTORY_DAYS = 20
"""Per Document 4 §10.1a's tree-based-model row: '20 trading days'
minimum ('needs enough rows to have engineered features at all')."""


@dataclass(frozen=True, slots=True)
class XgboostTrainResult:
    metrics: ClassificationMetrics
    feature_importances: dict[str, float]


class XgboostModel:
    """Wraps `xgboost.XGBClassifier` for binary buy(up)/sell(down)
    movement-probability classification over the engineered feature
    matrix — the second tree-based ensemble member alongside
    RandomForestModel, per Document 4 §10.2's gradient-boosted-trees row."""

    def __init__(self, n_estimators: int = 100, max_depth: int = 4) -> None:
        self._model = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            eval_metric="logloss",
        )
        self._feature_names: tuple[str, ...] = ()
        self._is_fitted = False

    @staticmethod
    def has_sufficient_history(n_rows: int) -> bool:
        return n_rows >= MINIMUM_HISTORY_DAYS

    def train(self, features: pd.DataFrame, labels: pd.Series) -> XgboostTrainResult:
        if len(features) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"XGBoost training requires at least {MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(features)}"
            )
        if features.empty or features.shape[1] == 0:
            raise ValueError("XGBoost training requires at least one feature column")

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
        return XgboostTrainResult(
            metrics=metrics, feature_importances={k: float(v) for k, v in importances.items()}
        )

    def predict_movement(self, features: pd.DataFrame) -> npt.NDArray[np.float64]:
        """Returns the predicted probability of UPWARD/BUY movement
        (class 1) for each row — Document 4's 'buy probability, sell
        probability, movement classification' requirement, expressed
        symmetrically to RandomForestModel.predict_movement() (buy
        probability = upward probability; sell probability = 1 - this)."""
        if not self._is_fitted:
            raise RuntimeError("XgboostModel.train() must be called before predict_movement()")
        probabilities = self._model.predict_proba(features)
        upward_index = int(np.where(self._model.classes_ == 1)[0][0])
        return np.asarray(probabilities[:, upward_index], dtype=np.float64)

    def predict_buy_sell_probabilities(
        self, features: pd.DataFrame
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        """Returns (buy_probability, sell_probability) arrays — the
        founder's explicit 'Buy Probability'/'Sell Probability' output
        pair, derived from the same underlying up/down classification
        (sell_probability = 1 - buy_probability, a proper complementary
        pair since this is a binary classifier, not two independent
        models)."""
        buy_probability = self.predict_movement(features)
        sell_probability = 1.0 - buy_probability
        return buy_probability, sell_probability

    def feature_importances(self) -> dict[str, float]:
        if not self._is_fitted:
            raise RuntimeError("XgboostModel.train() must be called before feature_importances()")
        return dict(
            zip(
                self._feature_names,
                (float(v) for v in self._model.feature_importances_),
                strict=True,
            )
        )

    def save(self, path: str | Path) -> None:
        if not self._is_fitted:
            raise RuntimeError("XgboostModel.train() must be called before save()")
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("wb") as f:
            pickle.dump({"model": self._model, "feature_names": self._feature_names}, f)

    @classmethod
    def load(cls, path: str | Path) -> XgboostModel:
        with Path(path).open("rb") as f:
            payload = pickle.load(f)  # noqa: S301 — trusted local artifact, matches ArimaModel.load's contract
        instance = cls()
        instance._model = payload["model"]
        instance._feature_names = payload["feature_names"]
        instance._is_fitted = True
        return instance
