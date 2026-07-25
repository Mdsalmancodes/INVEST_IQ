"""Prophet price-forecasting model — Document 4 §10.2's robust
seasonality/trend baseline that "handles missing data well." Per the
founder's Phase 7 instruction: long-term forecast, trend, seasonality,
holiday effects.

Per Document 4 §10.1a: Prophet minimum history = 30 trading days, below
which it degrades gracefully with wider uncertainty bands as data grows
(rather than being hard-excluded like LSTM/ARIMA below their thresholds —
this module still enforces a floor since Prophet's own fit is unstable
with too few points, but the threshold is Prophet's own, per the
architecture doc's per-model table).

ENVIRONMENT DISCLOSURE (see known-issues.md): Prophet requires a CmdStan
backend, which itself requires a C++ compiler + GNU Make. This machine has
neither installed (confirmed via a real `install_cmdstan` attempt — see
Phase 7 known-issues.md). This module's code is fully real (genuine
`prophet.Prophet()` calls, not stubbed) and will work correctly in any
environment with CmdStan available (e.g. the project's own Docker image).
`is_available()` performs a real availability probe so callers (the
Hybrid Decision Engine) can gracefully exclude Prophet from the ensemble
in environments where it cannot run — the same 'partialEnsemble' pattern
Document 4 §10.1a specifies for a model member being unavailable.
"""

from __future__ import annotations

import pickle
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from src.infrastructure.ml.models.metrics import RegressionMetrics

MINIMUM_HISTORY_DAYS = 30
"""Per Document 4 §10.1a's Prophet row: '30 trading days' minimum."""


@dataclass(frozen=True, slots=True)
class ProphetTrainResult:
    metrics: RegressionMetrics


@lru_cache(maxsize=1)
def is_available() -> bool:
    """Real runtime probe: attempts to fit a trivial Prophet model on a
    tiny synthetic series. Returns False (never raises) if the CmdStan
    backend is missing/broken in this environment — callers use this to
    decide whether to include Prophet in the ensemble at all, per
    Document 4 §10.1a's degraded-ensemble design. Cached since the probe
    itself is relatively expensive (a real model fit) and the answer
    cannot change within a single process's lifetime."""
    try:
        from prophet import Prophet

        probe_df = pd.DataFrame(
            {"ds": pd.date_range("2024-01-01", periods=35), "y": np.arange(35, dtype=float)}
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Prophet().fit(probe_df)
        return True
    except Exception:  # noqa: BLE001 — a broad, deliberate availability probe: ANY failure
        # (missing CmdStan, missing compiler, corrupted install) means
        # "not available," not a specific exception type we can predict.
        return False


class ProphetModel:
    """Wraps `prophet.Prophet`. Mirrors ArimaModel's persistence style
    (the fitted model object is pickled directly) since Prophet's own
    model_from_json serialization has version-compatibility caveats that
    plain pickling of the trusted local artifact avoids, matching this
    codebase's already-established 'trusted local artifact' pickle
    convention (see ArimaModel.save/load)."""

    def __init__(self) -> None:
        self._fitted_model: Any | None = None
        self._last_date: pd.Timestamp | None = None

    @staticmethod
    def has_sufficient_history(n_rows: int) -> bool:
        return n_rows >= MINIMUM_HISTORY_DAYS

    def train(
        self, dates: npt.NDArray[np.datetime64], close_prices: npt.NDArray[np.float64]
    ) -> ProphetTrainResult:
        if len(close_prices) < MINIMUM_HISTORY_DAYS:
            raise ValueError(
                f"Prophet training requires at least {MINIMUM_HISTORY_DAYS} rows, "
                f"got {len(close_prices)}"
            )
        if not is_available():
            raise RuntimeError(
                "Prophet is unavailable in this environment (CmdStan backend missing "
                "or broken) — see docs/phase-7/known-issues.md"
            )

        from prophet import Prophet

        df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": close_prices})
        split = max(MINIMUM_HISTORY_DAYS - 5, int(len(df) * 0.8))
        train_df, val_df = df.iloc[:split], df.iloc[split:]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = Prophet()
            model.fit(train_df)

        if len(val_df) > 0:
            future = model.make_future_dataframe(periods=len(val_df))
            forecast = model.predict(future)
            predicted = forecast["yhat"].to_numpy()[-len(val_df) :]
            metrics = RegressionMetrics.compute(val_df["y"].to_numpy(), predicted)
        else:
            forecast = model.predict(train_df)
            metrics = RegressionMetrics.compute(
                train_df["y"].to_numpy(), forecast["yhat"].to_numpy()
            )

        # Refit on the full series for actual serving, mirroring
        # ArimaModel's train/serve split rationale.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            full_model = Prophet()
            full_model.fit(df)

        self._fitted_model = full_model
        self._last_date = df["ds"].iloc[-1]
        return ProphetTrainResult(metrics=metrics)

    def predict_next(self, steps_ahead: int = 1) -> list[float]:
        if self._fitted_model is None:
            raise RuntimeError("ProphetModel.train() must be called before predict_next()")
        future = self._fitted_model.make_future_dataframe(periods=steps_ahead)
        forecast = self._fitted_model.predict(future)
        tail = forecast["yhat"].to_numpy()[-steps_ahead:]
        return [float(value) for value in tail]

    def save(self, path: str | Path) -> None:
        if self._fitted_model is None:
            raise RuntimeError("ProphetModel.train() must be called before save()")
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("wb") as f:
            pickle.dump({"fitted_model": self._fitted_model, "last_date": self._last_date}, f)

    @classmethod
    def load(cls, path: str | Path) -> ProphetModel:
        with Path(path).open("rb") as f:
            payload = pickle.load(f)  # noqa: S301 — trusted local artifact, matches ArimaModel.load's contract
        model = cls()
        model._fitted_model = payload["fitted_model"]
        model._last_date = payload["last_date"]
        return model
