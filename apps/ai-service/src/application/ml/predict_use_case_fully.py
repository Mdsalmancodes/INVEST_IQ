

from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src.application.ml.decision_engine import DecisionEngine, DecisionEngineResult
from src.infrastructure.ml.model_registry.model_loader import ModelLoader

from src.domain.ml.entities import Forecast, HorizonPoint, PredictionRun
from src.domain.ml.exceptions import InsufficientDataError
from src.domain.ml.repositories import MarketDataRepository, PredictionRunRepository
from src.domain.ml.value_objects import Confidence, ModelVersionId


DEFAULT_LOOKBACK_DAYS = 400

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
        model_loader: ModelLoader,
    ) -> None:
        self._market_data_repository = market_data_repository
        self._prediction_run_repository = prediction_run_repository
        self._model_loader = model_loader

    async def execute(self, command: PredictCommand) -> DecisionEngineResult:
        # ---------------- FETCH DATA ----------------
        end = date.today()
        start = end - timedelta(days=command.lookback_days)

        bars = await self._market_data_repository.get_ohlcv_bars(
            command.symbol, start, end
        )

        if not bars:
            raise InsufficientDataError(
                f"No OHLCV history available for {command.symbol!r}"
            )

        # ---------------- BUILD DATAFRAME ----------------
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

        # ---------------- LOAD MODELS ----------------
        models = await self._model_loader.load_all_models(command.symbol)

        # ---------------- CREATE ENGINE ----------------
        engine = DecisionEngine(
            lstm=models.get("lstm"),
            arima=models.get("arima"),
            prophet=models.get("prophet"),
            random_forest=models.get("random_forest"),
            xgboost=models.get("xgboost"),
            finbert=models.get("finbert"),
        )

        # ---------------- RUN ENGINE ----------------
        result = await asyncio.to_thread(
            engine.decide,
            command.symbol,
            ohlcv,
            command.news_texts,
        )

        # ---------------- SAVE RUN ----------------
        await self._prediction_run_repository.save(
            _to_prediction_run(result)
        )

        return result


def _to_prediction_run(result: DecisionEngineResult) -> PredictionRun:
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