"""Unit tests for PredictUseCase. Uses fake in-memory repositories with
the REAL DecisionEngine running the actual model pipeline on synthetic
OHLCV data — the repository fakes isolate this test from network/
filesystem concerns while the ML pipeline itself is exercised for real.
"""

from __future__ import annotations

import pytest

from src.application.ml.predict_use_case import PredictCommand, PredictUseCase
from src.domain.ml.exceptions import InsufficientDataError
from tests.unit.application.ml._fixtures import (
    FakeMarketDataRepository,
    FakePredictionRunRepository,
    synthetic_bars,
)


class TestPredictUseCase:
    async def test_raises_when_no_bars_available(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(())
        prediction_repo = FakePredictionRunRepository()
        use_case = PredictUseCase(market_data_repo, prediction_repo)

        with pytest.raises(InsufficientDataError, match="No OHLCV history"):
            await use_case.execute(PredictCommand(symbol="AAPL"))

    async def test_produces_and_persists_a_recommendation(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        prediction_repo = FakePredictionRunRepository()
        use_case = PredictUseCase(market_data_repo, prediction_repo)

        result = await use_case.execute(PredictCommand(symbol="aapl"))

        assert result.recommendation.symbol == "AAPL"
        assert result.recommendation.verdict in {"buy", "sell", "hold"}
        assert len(prediction_repo.saved) == 1
        assert prediction_repo.saved[0].symbol == "AAPL"

    async def test_includes_finbert_when_news_texts_provided(self) -> None:
        market_data_repo = FakeMarketDataRepository.with_default_bars(synthetic_bars(100))
        prediction_repo = FakePredictionRunRepository()
        use_case = PredictUseCase(market_data_repo, prediction_repo)

        result = await use_case.execute(
            PredictCommand(symbol="AAPL", news_texts=["Strong earnings beat estimates."])
        )

        assert "finbert" not in result.excluded_models
