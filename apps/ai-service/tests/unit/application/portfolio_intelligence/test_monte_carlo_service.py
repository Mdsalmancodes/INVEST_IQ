"""Unit tests for MonteCarloService — Phase 10 Monte Carlo Simulation."""

from __future__ import annotations

import pytest

from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.monte_carlo_service import (
    InvalidSimulationRunCountError,
    MonteCarloService,
)
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


async def _build_returns_data(holdings: list[PortfolioHoldingInput]) -> object:
    repo = FakeMarketDataRepository(
        bars_by_symbol={h.symbol: synthetic_bars(120, seed=hash(h.symbol) % 1000) for h in holdings}
    )
    return await fetch_holdings_returns(repo, holdings)


class TestMonteCarloService:
    @pytest.mark.parametrize("num_runs", [100, 500, 1000, 5000])
    async def test_supports_every_founder_specified_run_count(self, num_runs: int) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result = service.simulate(data, num_runs=num_runs, seed=42)

        assert result.num_runs == num_runs
        assert len(result.final_value_distribution) == num_runs

    async def test_rejects_an_unsupported_run_count(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        with pytest.raises(InvalidSimulationRunCountError):
            service.simulate(data, num_runs=250)

    async def test_produces_worst_expected_and_best_case_in_ascending_order(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result = service.simulate(data, num_runs=1000, seed=42)

        assert result.worst_case_value <= result.expected_case_value <= result.best_case_value

    async def test_confidence_intervals_start_at_the_known_starting_value(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result = service.simulate(data, num_runs=500, seed=42)

        day_zero = result.confidence_intervals[0]
        assert day_zero.day == 0
        assert day_zero.p5 == day_zero.p50 == day_zero.p95 == result.starting_value

    async def test_confidence_intervals_include_the_final_horizon_day(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result = service.simulate(data, num_runs=100, horizon_days=100, seed=42)

        assert result.confidence_intervals[-1].day == 100

    async def test_each_confidence_interval_has_ascending_percentile_bands(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result = service.simulate(data, num_runs=1000, seed=42)

        for interval in result.confidence_intervals:
            assert interval.p5 <= interval.p25 <= interval.p50 <= interval.p75 <= interval.p95

    async def test_is_deterministic_given_the_same_seed(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = MonteCarloService()

        result_a = service.simulate(data, num_runs=100, seed=7)
        result_b = service.simulate(data, num_runs=100, seed=7)

        assert result_a.final_value_distribution == result_b.final_value_distribution

    async def test_empty_holdings_produce_a_flat_result_at_the_starting_value(self) -> None:
        data = await _build_returns_data([])
        service = MonteCarloService()

        result = service.simulate(data, num_runs=100, seed=42)

        assert result.starting_value == 0.0
        assert result.worst_case_value == 0.0
        assert result.expected_case_value == 0.0
        assert result.best_case_value == 0.0
        assert all(v == 0.0 for v in result.final_value_distribution)
