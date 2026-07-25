"""Unit tests for FileSystemPredictionRunRepository."""

from __future__ import annotations

from src.domain.ml.entities import Forecast, HorizonPoint, PredictionRun
from src.domain.ml.value_objects import (
    Confidence,
    ExplainabilityPayload,
    FeatureContribution,
    ModelVersionId,
)
from src.infrastructure.persistence.prediction_run_repository import (
    FileSystemPredictionRunRepository,
)


def _prediction_run(symbol: str = "AAPL") -> PredictionRun:
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
        reasoning="Test reasoning.",
    )
    return PredictionRun.create(
        symbol=symbol,
        member_forecasts=(forecast,),
        ensemble_price=151.0,
        ensemble_confidence=Confidence(0.75),
        data_quality="full",
        explainability=explainability,
    )


class TestFileSystemPredictionRunRepositorySaveAndGet:
    async def test_save_and_get_by_id_round_trips(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        run = _prediction_run()

        await repo.save(run)
        fetched = await repo.get_by_id(run.id)

        assert fetched is not None
        assert fetched.symbol == "AAPL"
        assert fetched.ensemble_price == 151.0
        assert len(fetched.member_forecasts) == 1
        assert fetched.member_forecasts[0].model_family == "lstm"
        assert fetched.explainability.reasoning == "Test reasoning."

    async def test_get_by_id_returns_none_when_not_found(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        run = _prediction_run()
        result = await repo.get_by_id(run.id)
        assert result is None

    async def test_save_is_append_only_never_overwrites(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        first = _prediction_run()
        second = _prediction_run()
        await repo.save(first)
        await repo.save(second)

        path = tmp_path / "AAPL.jsonl"
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2


class TestFileSystemPredictionRunRepositoryListForSymbol:
    async def test_returns_empty_tuple_when_no_runs_exist(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        results = await repo.list_for_symbol("AAPL")
        assert results == ()

    async def test_returns_most_recent_first(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        first = _prediction_run()
        second = _prediction_run()
        await repo.save(first)
        await repo.save(second)

        results = await repo.list_for_symbol("AAPL")

        assert len(results) == 2
        assert results[0].id == second.id
        assert results[1].id == first.id

    async def test_respects_limit(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        for _ in range(5):
            await repo.save(_prediction_run())

        results = await repo.list_for_symbol("AAPL", limit=3)

        assert len(results) == 3

    async def test_is_case_insensitive_on_symbol(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        repo = FileSystemPredictionRunRepository(tmp_path)
        await repo.save(_prediction_run(symbol="aapl"))

        results = await repo.list_for_symbol("aapl")

        assert len(results) == 1
