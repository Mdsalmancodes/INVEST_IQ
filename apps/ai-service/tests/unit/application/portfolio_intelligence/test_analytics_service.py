"""Unit tests for AnalyticsService — Phase 10 Portfolio Analytics."""

from __future__ import annotations

from src.application.portfolio_intelligence.analytics_service import AnalyticsService
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


async def _build_returns_data(holdings: list[PortfolioHoldingInput]) -> object:
    repo = FakeMarketDataRepository(
        bars_by_symbol={h.symbol: synthetic_bars(100, seed=hash(h.symbol) % 1000) for h in holdings}
    )
    return await fetch_holdings_returns(repo, holdings)


class TestAnalyticsService:
    async def test_computes_a_full_analytics_result_for_a_diversified_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech"),
            PortfolioHoldingInput(
                symbol="JNJ", quantity=5, market_value=500.0, sector="Healthcare"
            ),
            PortfolioHoldingInput(
                symbol="XOM", quantity=8, market_value=500.0, sector="Energy"
            ),
        ]
        data = await _build_returns_data(holdings)
        service = AnalyticsService()

        result = service.compute(data)

        assert 0.0 <= result.health_score <= 100.0
        assert 0.0 <= result.diversification_score <= 100.0
        assert 0.0 <= result.risk_score <= 100.0
        assert 0.0 <= result.concentration_risk <= 1.0
        assert len(result.sector_exposure) == 3
        assert len(result.asset_allocation) == 3
        assert result.correlation_matrix.symbols == ("AAPL", "JNJ", "XOM") or set(
            result.correlation_matrix.symbols
        ) == {"AAPL", "JNJ", "XOM"}
        assert len(result.historical_performance) > 0
        assert result.annualized_volatility_pct >= 0.0

    async def test_sector_exposure_sums_to_100_percent(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=600.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=400.0, sector="Tech"),
        ]
        data = await _build_returns_data(holdings)
        service = AnalyticsService()

        result = service.compute(data)

        # Both holdings share the same sector — a single sector bucket at 100%.
        assert len(result.sector_exposure) == 1
        assert result.sector_exposure[0].sector == "Tech"
        assert abs(result.sector_exposure[0].allocation_pct - 100.0) < 0.01

    async def test_a_holding_with_no_sector_is_grouped_under_unknown(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=500.0, sector=None)
        ]
        data = await _build_returns_data(holdings)
        service = AnalyticsService()

        result = service.compute(data)

        assert result.sector_exposure[0].sector == "Unknown"

    async def test_a_single_holding_portfolio_has_maximum_concentration_risk(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await _build_returns_data(holdings)
        service = AnalyticsService()

        result = service.compute(data)

        assert result.concentration_risk == 1.0
        assert result.correlation_matrix.matrix == ((1.0,),)

    async def test_empty_holdings_produce_a_well_formed_zeroed_result(self) -> None:
        data = await _build_returns_data([])
        service = AnalyticsService()

        result = service.compute(data)

        assert result.sector_exposure == ()
        assert result.asset_allocation == ()
        assert result.concentration_risk == 0.0
        assert result.correlation_matrix.symbols == ()
        assert result.historical_performance == ()
        assert result.daily_return_pct is None
        assert result.cagr_pct is None

    async def test_period_returns_are_none_when_history_is_too_short(self) -> None:
        repo = FakeMarketDataRepository(bars_by_symbol={"AAPL": synthetic_bars(3, seed=1)})
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data = await fetch_holdings_returns(repo, holdings)
        service = AnalyticsService()

        result = service.compute(data)

        # Only 2 daily returns available (3 bars -> 2 pct_change values) —
        # not enough for a full trading week (5) or month (21).
        assert result.weekly_return_pct is None
        assert result.monthly_return_pct is None
