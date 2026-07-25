"""ARIMA price-forecasting model — Document 4 §10.2's classical
statistical baseline, useful for short-horizon, low-volatility regimes.
Per the founder's Phase 7 instruction: statistical time-series
forecasting, trend analysis, seasonality; used to compare against LSTM.

Per Document 4 §10.1a: ARIMA minimum history = 20 trading days, below
which it is excluded from the ensemble entirely.
"""

from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from statsmodels.tsa.arima.model import ARIMA

from src.infrastructure.ml.models.metrics import RegressionMetrics

MINIMUM_HISTORY_DAYS = 20
"""Per Document 4 §10.1a's ARIMA row: '20 trading days' minimum."""

DEFAULT_ORDER = (5, 1, 0)
"""(p, d, q) — 5 autoregressive lags, first-differenced (handles a
trending, non-stationary price series without a separate stationarity
test/transform step), no moving-average terms. A deliberately simple,
well-understood default rather than an auto-ARIMA search, matching this
phase's "real but minimal" scope for the statistical baseline member."""


@dataclass(frozen=True, slots=True)
class ArimaTrainResult:
    metrics: RegressionMetrics
    order: tuple[int, int, int]


class ArimaModel:
    """Wraps `statsmodels.tsa.arima.model.ARIMA`. Unlike LstmModel, ARIMA
    is refit on the full history at inference time rather than loaded as
    a fixed weight snapshot — this is standard ARIMA practice (the fitted
    parameters are a function of the exact series, not a
    generalizable-across-series model), so `save()`/`load()` persist the
    fitted statsmodels results object directly."""

    def __init__(self, order: tuple[int, int, int] = DEFAULT_ORDER) -> None:
        self._order = order
        self._fitted_result: Any | None = None

    @staticmethod
    def has_sufficient_history(n_rows: int) -> bool:
        return n_rows >= MINIMUM_HISTORY_DAYS

    def train(self, close_prices: npt.NDArray[np.float64]) -> ArimaTrainResult:
        if len(close_prices) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"ARIMA training requires at least {MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(close_prices)}"
            )

        split = max(MINIMUM_HISTORY_DAYS - 5, int(len(close_prices) * 0.8))
        train_prices = close_prices[:split]
        val_prices = close_prices[split:]

        with warnings.catch_warnings():
            # statsmodels emits a ConvergenceWarning/UserWarning for small
            # sample sizes, which is expected and disclosed for this
            # phase's real-but-small training datasets — not silenced
            # globally, just scoped to this fit call.
            warnings.simplefilter("ignore")
            model = ARIMA(train_prices, order=self._order)
            self._fitted_result = model.fit()

        if len(val_prices) > 0:
            forecast = self._fitted_result.forecast(steps=len(val_prices))
            metrics = RegressionMetrics.compute(val_prices, np.asarray(forecast))
        else:
            # Not enough data for a held-out validation split — report
            # in-sample residual error instead of fabricating a metric.
            fitted_values = np.asarray(self._fitted_result.fittedvalues)
            metrics = RegressionMetrics.compute(train_prices, fitted_values)

        # Refit on the FULL series for actual forecasting use — the
        # train/val split above is only for reporting held-out metrics,
        # matching how LstmModel reports validation metrics from a held-out
        # slice but ultimately serves predictions from a model fit on all
        # available history.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            full_model = ARIMA(close_prices, order=self._order)
            self._fitted_result = full_model.fit()

        return ArimaTrainResult(metrics=metrics, order=self._order)

    def predict_next(self, steps_ahead: int = 1) -> list[float]:
        if self._fitted_result is None:
            raise RuntimeError("ArimaModel.train() must be called before predict_next()")
        forecast = self._fitted_result.forecast(steps=steps_ahead)
        return [float(value) for value in np.asarray(forecast)]

    def save(self, path: str | Path) -> None:
        if self._fitted_result is None:
            raise RuntimeError("ArimaModel.train() must be called before save()")
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("wb") as f:
            pickle.dump({"order": self._order, "fitted_result": self._fitted_result}, f)

    @classmethod
    def load(cls, path: str | Path) -> ArimaModel:
        with Path(path).open("rb") as f:
            payload = pickle.load(f)  # noqa: S301 — trusted local artifact, matches LstmModel.load's torch.load contract
        model = cls(order=payload["order"])
        model._fitted_result = payload["fitted_result"]
        return model
