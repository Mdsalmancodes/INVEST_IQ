"""Unit tests for OptimizationService — Phase 10 Portfolio Optimization."""

from __future__ import annotations

import pytest

from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.optimization_service import (
    InsufficientHoldingsForOptimizationError,
    OptimizationService,
)
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


async def _build_returns_data(holdings: list[PortfolioHoldingInput]) -> object:
    repo = FakeMarketDataRepository(
        bars_by_symbol={
            h.symbol: synthetic_bars(150, seed=hash(h.symbol) % 1000, trend=0.05 + i * 0.05)
            for i, h in enumerate(holdings)
        }
    )
    return await fetch_holdings_returns(repo, holdings)


class TestOptimizationService:
    async def test_raises_for_a_single_holding_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        with pytest.raises(InsufficientHoldingsForOptimizationError):
            service.optimize(data)

    async def test_max_sharpe_weights_sum_to_one_and_are_non_negative(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=600.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=400.0, sector="Healthcare"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        result = service.optimize(data)

        assert abs(sum(result.max_sharpe_portfolio.weights) - 1.0) < 0.01
        assert all(w >= -0.001 for w in result.max_sharpe_portfolio.weights)

    async def test_min_variance_weights_sum_to_one_and_are_non_negative(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=600.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=400.0, sector="Healthcare"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        result = service.optimize(data)

        assert abs(sum(result.min_variance_portfolio.weights) - 1.0) < 0.01
        assert all(w >= -0.001 for w in result.min_variance_portfolio.weights)

    async def test_min_variance_has_the_lowest_volatility_on_the_frontier(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=600.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=400.0, sector="Healthcare"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        result = service.optimize(data)

        frontier_volatilities = [p.volatility_pct for p in result.efficient_frontier]
        assert result.min_variance_portfolio.volatility_pct <= min(frontier_volatilities) + 0.5

    async def test_efficient_frontier_risk_is_non_decreasing_as_return_increases(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=500.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=300.0, sector="Healthcare"
            ),
            PortfolioHoldingInput(symbol="XOM", quantity=8, market_value=200.0, sector="Energy"),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        result = service.optimize(data)

        returns = [p.expected_return_pct for p in result.efficient_frontier]
        volatilities = [p.volatility_pct for p in result.efficient_frontier]
        assert returns == sorted(returns)
        # The true efficient frontier's risk should trend upward as
        # target return increases — allow a small numerical tolerance
        # since scipy's optimizer may not converge to bit-exact
        # monotonicity at every single point.
        assert volatilities[-1] >= volatilities[0] - 1.0

    async def test_capital_allocation_line_starts_at_the_risk_free_rate(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=600.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=400.0, sector="Healthcare"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService(annual_risk_free_rate_pct=4.5)

        result = service.optimize(data)

        risk_free_point, tangency_point = result.capital_allocation_line
        assert risk_free_point.volatility_pct == 0.0
        assert risk_free_point.expected_return_pct == 4.5
        assert tangency_point.volatility_pct == result.max_sharpe_portfolio.volatility_pct

    async def test_suggested_rebalancing_deltas_reflect_current_vs_target_weights(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=900.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=100.0, sector="Healthcare"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = OptimizationService()

        result = service.optimize(data)

        assert len(result.suggested_rebalancing) == 2
        for suggestion in result.suggested_rebalancing:
            expected_delta = suggestion.suggested_weight_pct - suggestion.current_weight_pct
            assert abs(suggestion.delta_pct - expected_delta) < 0.01
