"""Unit tests for PredictionHistoryUseCase."""

from __future__ import annotations

from src.application.ml.prediction_history_use_case import (
    PredictionHistoryQuery,
    PredictionHistoryUseCase,
)
from src.domain.ml.entities import PredictionRun
from src.domain.ml.value_objects import Confidence, ExplainabilityPayload, FeatureContribution
from tests.unit.application.ml._fixtures import FakePredictionRunRepository


def _prediction_run(symbol: str = "AAPL") -> PredictionRun:
    from src.domain.ml.entities import Forecast, HorizonPoint
    from src.domain.ml.value_objects import ModelVersionId

    forecast = Forecast.create(
        symbol=symbol,
        model_family="lstm",
        model_version_id=ModelVersionId.new(),
        points=(
            HorizonPoint(horizon_days=1, predicted_price=150.0, lower_bound=145, upper_bound=155),
        ),
        confidence=Confidence(0.8),
        data_quality="full",
    )
    explainability = ExplainabilityPayload(
        top_contributions=(FeatureContribution(name="rsi14", value=0.12),),
        base_value=0.5,
        method="weighted_ensemble_vote",
        reasoning="Test.",
    )
    return PredictionRun.create(
        symbol=symbol,
        member_forecasts=(forecast,),
        ensemble_price=151.0,
        ensemble_confidence=Confidence(0.75),
        data_quality="full",
        explainability=explainability,
    )


class TestPredictionHistoryUseCase:
    async def test_returns_empty_tuple_when_no_history_exists(self) -> None:
        repo = FakePredictionRunRepository()
        use_case = PredictionHistoryUseCase(repo)

        result = await use_case.execute(PredictionHistoryQuery(symbol="AAPL"))

        assert result == ()

    async def test_returns_history_most_recent_first(self) -> None:
        repo = FakePredictionRunRepository()
        first = _prediction_run()
        second = _prediction_run()
        await repo.save(first)
        await repo.save(second)
        use_case = PredictionHistoryUseCase(repo)

        result = await use_case.execute(PredictionHistoryQuery(symbol="AAPL"))

        assert len(result) == 2
        assert result[0].id == second.id
        assert result[1].id == first.id

    async def test_respects_limit(self) -> None:
        repo = FakePredictionRunRepository()
        for _ in range(5):
            await repo.save(_prediction_run())
        use_case = PredictionHistoryUseCase(repo)

        result = await use_case.execute(PredictionHistoryQuery(symbol="AAPL", limit=2))

        assert len(result) == 2
