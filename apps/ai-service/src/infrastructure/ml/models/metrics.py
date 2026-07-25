"""Shared evaluation-metrics dataclass — every model wrapper's train()
returns one of these, giving the Decision Engine and Model Registry a
uniform way to compare heterogeneous model families (Document 4 §10.8's
`validation_metrics` field)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class RegressionMetrics:
    rmse: float
    mae: float

    @classmethod
    def compute(
        cls, actual: npt.NDArray[np.float64], predicted: npt.NDArray[np.float64]
    ) -> RegressionMetrics:
        errors = actual - predicted
        rmse = float(np.sqrt(np.mean(errors**2)))
        mae = float(np.mean(np.abs(errors)))
        return cls(rmse=rmse, mae=mae)

    def as_dict(self) -> dict[str, float]:
        return {"rmse": self.rmse, "mae": self.mae}


@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    accuracy: float
    directional_accuracy: float

    @classmethod
    def compute(
        cls, actual: npt.NDArray[np.float64], predicted: npt.NDArray[np.float64]
    ) -> ClassificationMetrics:
        accuracy = float(np.mean(actual == predicted))
        return cls(accuracy=accuracy, directional_accuracy=accuracy)

    def as_dict(self) -> dict[str, float]:
        return {"accuracy": self.accuracy, "directional_accuracy": self.directional_accuracy}
