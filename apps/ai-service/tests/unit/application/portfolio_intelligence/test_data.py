"""Unit tests for fetch_holdings_returns() — the shared data-fetching
helper every Phase 10 quantitative use case builds on."""

from __future__ import annotations

from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


class TestFetchHoldingsReturns:
    async def test_computes_daily_returns_and_weights_for_each_holding(self) -> None:
        repo = FakeMarketDataRepository(
            bars_by_symbol={
                "AAPL": synthetic_bars(100, seed=1),
                "MSFT": synthetic_bars(100, seed=2),
            }
        )
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1500.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=500.0, sector="Tech"),
        ]

        result = await fetch_holdings_returns(repo, holdings)

        assert result.total_market_value == 2000.0
        assert len(result.holdings) == 2
        aapl = next(h for h in result.holdings if h.symbol == "AAPL")
        assert aapl.weight == 0.75
        assert aapl.sector == "Tech"
        assert not aapl.daily_returns.empty

    async def test_excludes_a_holding_with_no_market_data(self) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(100, seed=1)})
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="UNKNOWN", quantity=1, market_value=100.0, sector="Unknown"
            ),
        ]

        result = await fetch_holdings_returns(repo, holdings)

        assert len(result.holdings) == 1
        assert result.holdings[0].symbol == "AAPL"
        # total_market_value still reflects ALL supplied holdings (weights
        # are computed against the true total, not just the ones with data).
        assert result.total_market_value == 1100.0

    async def test_excludes_a_holding_with_fewer_than_two_bars(self) -> None:
        repo = FakeMarketDataRepository(
            bars_by_symbol={"AAPL": synthetic_bars(1, seed=1)}
        )
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]

        result = await fetch_holdings_returns(repo, holdings)

        assert result.holdings == ()

    async def test_returns_empty_when_total_market_value_is_zero(self) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(100, seed=1)})
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=0.0, sector="Tech")
        ]

        result = await fetch_holdings_returns(repo, holdings)

        assert result.total_market_value == 0.0
        assert result.holdings[0].weight == 0.0
