"""PredictUseCase — the application-layer entry point backing both the
"Predict" and "Buy/Sell/Hold Recommendation" API endpoints (the founder's
instruction lists them separately, but a `Recommendation`'s `verdict`
field IS the buy/sell/hold answer — Document 4 §10.4 does not specify two
different computations for these, so both endpoints call this same use
case, matching how this codebase avoids duplicating identical business
logic under two names).

Orchestrates: fetch OHLCV history via MarketDataRepository (never
duplicating core-api's Market Data module, per the founder's instruction)
-> run the Hybrid Decision Engine -> persist the resulting PredictionRun
(Document 4 §10.2 step 4's "never overwritten" immutable record) -> return
the full DecisionEngineResult for the presentation layer to shape into a
response.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src.application.ml.decision_engine import DecisionEngine, DecisionEngineResult
from src.domain.ml.entities import Forecast, HorizonPoint, PredictionRun
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import MarketDataRepository, PredictionRunRepository
from src.domain.ml.value_objects import Confidence, ModelVersionId

DEFAULT_LOOKBACK_DAYS = 400
"""Comfortably covers LSTM's 90-day minimum plus its own 60-day lookback
window, with headroom for weekends/holidays in the fetched calendar range
(Document 4 §10.1a's LSTM row) — a generous default, not a tight minimum,
since fetching "a bit more than needed" is cheap and this use case has no
way to know in advance which model families will actually run for a given
symbol."""


@dataclass(frozen=True, slots=True)
class PredictCommand:
    symbol: str
    news_texts: list[str] | None = None
    lookback_days: int = DEFAULT_LOOKBACK_DAYS


class PredictUseCase:
    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        prediction_run_repository: PredictionRunRepository,
        decision_engine: DecisionEngine | None = None,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._prediction_run_repository = prediction_run_repository
        self._decision_engine = decision_engine or DecisionEngine()

    async def execute(self, command: PredictCommand) -> DecisionEngineResult:
        end = date.today()
        start = end - timedelta(days=command.lookback_days)
        bars = await self._market_data_repository.get_ohlcv_bars(command.symbol, start, end)

        if not bars:
            raise InsufficientDataError(
                f"No OHLCV history available for {command.symbol!r} — cannot run the "
                f"Hybrid Decision Engine"
            )

        ohlcv = pd.DataFrame(
            {
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            },
            index=pd.DatetimeIndex([b.bar_time for b in bars]),
        )

        # DecisionEngine.decide() synchronously trains up to 5 models
        # (LSTM/ARIMA/Prophet/RandomForest/XGBoost) — genuinely CPU-bound
        # work that would otherwise block this coroutine's event loop for
        # the full training duration on every /predict and /recommendation
        # call, starving every other concurrent request this ai-service
        # instance is serving. asyncio.to_thread() runs it on the default
        # executor's worker thread pool instead, keeping the event loop
        # free. This is a request-latency/concurrency fix only — it does
        # not change decide()'s inputs, outputs, or exception behavior.
        result = await asyncio.to_thread(
            self._decision_engine.decide, command.symbol, ohlcv, command.news_texts
        )
        await self._prediction_run_repository.save(_to_prediction_run(result))
        return result


def _to_prediction_run(result: DecisionEngineResult) -> PredictionRun:
    """The DecisionEngine's Recommendation is not itself a PredictionRun
    (Document 4 §10.2's immutable per-instrument record persists the
    member Forecasts + ensemble outcome, distinct from the Recommendation
    entity, which is the Decision Engine's buy/sell/hold synthesis).
    Building the PredictionRun record here keeps that construction
    concern in the application layer, where it has access to both the
    Recommendation and the raw per-model signals needed to assemble it."""
    member_forecasts = tuple(
        Forecast.create(
            symbol=result.recommendation.symbol,
            model_family=signal.model_family,
            model_version_id=ModelVersionId.new(),
            points=(
                HorizonPoint(
                    horizon_days=1,
                    predicted_price=result.price_forecast_1d,
                    lower_bound=result.price_forecast_1d * 0.95,
                    upper_bound=result.price_forecast_1d * 1.05,
                ),
            ),
            confidence=Confidence(round(signal.confidence, 4)),
            data_quality=result.recommendation.data_quality,
        )
        for signal in result.member_signals
    )
    return PredictionRun.create(
        symbol=result.recommendation.symbol,
        member_forecasts=member_forecasts,
        ensemble_price=result.price_forecast_1d,
        ensemble_confidence=result.recommendation.confidence,
        data_quality=result.recommendation.data_quality,
        explainability=result.recommendation.explainability,
    )
