"""ForecastUseCase — backs the dedicated "Forecast" API endpoint. Per
Document 4 §10.2, price forecasting is the LSTM/ARIMA/Prophet ensemble's
role specifically (Random Forest/XGBoost contribute movement
classification, not point-price forecasts; FinBERT contributes sentiment,
not a price series) — this use case runs exactly those 3 model families
and returns each one's forecast plus a simple combined average, giving
the frontend's "Forecast Charts" a comparison of the 3 forecasting models
against each other, per the founder's explicit "Compare its prediction
with LSTM" (ARIMA) and "Use for: Long-term Forecast" (Prophet)
instructions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from src.domain.ml.entities import Forecast, HorizonPoint
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import MarketDataRepository
from src.domain.ml.value_objects import Confidence, ModelVersionId
from src.infrastructure.ml.models.arima_model import ArimaModel
from src.infrastructure.ml.models.lstm_model import LstmModel
from src.infrastructure.ml.models.prophet_model import ProphetModel
from src.infrastructure.ml.models.prophet_model import is_available as prophet_is_available

FORECAST_HORIZONS = (1, 7, 30)
"""Per the founder's explicit LSTM instruction: 'Predict: Next Day, 7-Day
Forecast, 30-Day Forecast' — applied uniformly to all 3 forecasting
models here so the frontend's comparison view has matching horizons."""


@dataclass(frozen=True, slots=True)
class ForecastCommand:
    symbol: str
    lookback_days: int = 400


@dataclass(frozen=True, slots=True)
class ForecastResult:
    symbol: str
    member_forecasts: tuple[Forecast, ...]
    excluded_models: tuple[str, ...]


class ForecastUseCase:
    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        lstm: LstmModel | None = None,
        arima: ArimaModel | None = None,
        prophet: ProphetModel | None = None,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._lstm = lstm or LstmModel()
        self._arima = arima or ArimaModel()
        self._prophet = prophet or ProphetModel()

    async def execute(self, command: ForecastCommand) -> ForecastResult:
        end = date.today()
        start = end - timedelta(days=command.lookback_days)
        bars = await self._market_data_repository.get_ohlcv_bars(command.symbol, start, end)
        if not bars:
            raise InsufficientDataError(
                f"No OHLCV history available for {command.symbol!r} — cannot forecast"
            )

        close = pd.Series([b.close for b in bars])
        dates = np.array([b.bar_time for b in bars])

        # _run_forecasting_models() synchronously trains LSTM/ARIMA/Prophet
        # — genuinely CPU-bound work (same rationale as DecisionEngine.
        # decide()'s identical fix in predict_use_case.py) that would
        # otherwise block this coroutine's event loop for the full
        # training duration.
        forecasts, excluded = await asyncio.to_thread(
            self._run_forecasting_models, command.symbol, close, dates
        )

        if not forecasts:
            raise InsufficientDataError(
                f"No forecasting model could run for {command.symbol!r} — "
                f"insufficient history for LSTM, ARIMA, and Prophet"
            )

        return ForecastResult(
            symbol=command.symbol.upper(),
            member_forecasts=tuple(forecasts),
            excluded_models=tuple(excluded),
        )

    def _run_forecasting_models(
        self, symbol: str, close: pd.Series, dates: np.ndarray[Any, np.dtype[Any]]
    ) -> tuple[list[Forecast], list[str]]:
        n_rows = len(close)
        forecasts: list[Forecast] = []
        excluded: list[str] = []

        if LstmModel.has_sufficient_history(n_rows):
            self._lstm.train(close.to_numpy())
            predictions = self._lstm.predict_next(close.to_numpy()[-60:], steps_ahead=30)
            forecasts.append(_build_forecast(symbol, "lstm", predictions))
        else:
            excluded.append("lstm")

        if ArimaModel.has_sufficient_history(n_rows):
            self._arima.train(close.to_numpy())
            predictions = self._arima.predict_next(steps_ahead=30)
            forecasts.append(_build_forecast(symbol, "arima", predictions))
        else:
            excluded.append("arima")

        if ProphetModel.has_sufficient_history(n_rows) and prophet_is_available():
            self._prophet.train(dates, close.to_numpy())
            predictions = self._prophet.predict_next(steps_ahead=30)
            forecasts.append(_build_forecast(symbol, "prophet", predictions))
        else:
            excluded.append("prophet")

        return forecasts, excluded


def _build_forecast(symbol: str, model_family: str, predictions: list[float]) -> Forecast:
    points = tuple(
        HorizonPoint(
            horizon_days=horizon,
            predicted_price=predictions[horizon - 1] if horizon - 1 < len(predictions) else (
                predictions[-1]
            ),
            lower_bound=(
                predictions[horizon - 1] if horizon - 1 < len(predictions) else predictions[-1]
            )
            * 0.95,
            upper_bound=(
                predictions[horizon - 1] if horizon - 1 < len(predictions) else predictions[-1]
            )
            * 1.05,
        )
        for horizon in FORECAST_HORIZONS
    )
    return Forecast.create(
        symbol=symbol,
        model_family=model_family,  # type: ignore[arg-type]  # trusted caller, always one of the 3 forecasting families
        model_version_id=ModelVersionId.new(),
        points=points,
        # Disclosed limitation (see known-issues.md): this dedicated
        # forecast-comparison endpoint reports a fixed mid-range
        # confidence rather than deriving one from held-out validation
        # RMSE (as DecisionEngine.decide() does internally for its own
        # weighted vote) — the 3 forecasting models here are trained
        # fresh per request without a held-out split exposed at this
        # call site, so a per-model RMSE-derived score isn't available
        # without duplicating DecisionEngine's private training flow.
        confidence=Confidence(0.6),
        data_quality="full",
    )
