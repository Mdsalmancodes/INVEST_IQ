"""Unit tests for PortfolioRecommendationUseCase."""

from __future__ import annotations

import pytest

from src.application.ml.portfolio_recommendation_use_case import (
    PortfolioHolding,
    PortfolioRecommendationCommand,
    PortfolioRecommendationUseCase,
)
from src.domain.ml.exceptions import InsufficientDataError
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


class TestPortfolioRecommendationUseCase:
    async def test_raises_when_no_holdings_provided(self) -> None:
        market_data_repo = FakeMarketDataRepository()
        use_case = PortfolioRecommendationUseCase(market_data_repo)

        with pytest.raises(InsufficientDataError, match="at least one holding"):
            await use_case.execute(PortfolioRecommendationCommand(holdings=[]))

    async def test_raises_when_no_holding_has_data(self) -> None:
        market_data_repo = FakeMarketDataRepository(bars_by_symbol={})
        use_case = PortfolioRecommendationUseCase(market_data_repo)

        with pytest.raises(InsufficientDataError, match="sufficient market data"):
            await use_case.execute(
                PortfolioRecommendationCommand(
                    holdings=[PortfolioHolding(symbol="AAPL", quantity=10)]
                )
            )

    async def test_evaluates_all_holdings_with_data(self) -> None:
        market_data_repo = FakeMarketDataRepository(
            bars_by_symbol={
                "AAPL": synthetic_bars(100, seed=1),
                "MSFT": synthetic_bars(100, seed=2),
            }
        )
        use_case = PortfolioRecommendationUseCase(market_data_repo)

        result = await use_case.execute(
            PortfolioRecommendationCommand(
                holdings=[
                    PortfolioHolding(symbol="AAPL", quantity=10),
                    PortfolioHolding(symbol="MSFT", quantity=5),
                ]
            )
        )

        assert len(result.items) == 2
        assert result.overall_verdict in {"buy", "sell", "hold"}
        assert -1.0 <= result.overall_sentiment_score <= 1.0

    async def test_skips_holdings_without_market_data(self) -> None:
        market_data_repo = FakeMarketDataRepository(
            bars_by_symbol={"AAPL": synthetic_bars(100, seed=1)}
        )
        use_case = PortfolioRecommendationUseCase(market_data_repo)

        result = await use_case.execute(
            PortfolioRecommendationCommand(
                holdings=[
                    PortfolioHolding(symbol="AAPL", quantity=10),
                    PortfolioHolding(symbol="UNKNOWN", quantity=5),
                ]
            )
        )

        assert len(result.items) == 1
        assert result.items[0].symbol == "AAPL"
