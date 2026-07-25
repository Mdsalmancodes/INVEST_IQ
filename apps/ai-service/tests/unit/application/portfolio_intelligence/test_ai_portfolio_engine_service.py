"""Unit tests for AiPortfolioEngineService — Phase 10 AI Portfolio Engine."""

from __future__ import annotations

from src.application.portfolio_intelligence.ai_portfolio_engine_service import (
    AiPortfolioEngineService,
)
from src.application.portfolio_intelligence.analytics_service import AnalyticsService
from src.application.portfolio_intelligence.data import (
    PortfolioHoldingInput,
    fetch_holdings_returns,
)
from src.application.portfolio_intelligence.risk_metrics_service import RiskMetricsService
from tests.unit.application.ml._fixtures import FakeMarketDataRepository, synthetic_bars


async def _build_bundle(holdings: list[PortfolioHoldingInput]) -> tuple:
    bars_by_symbol = {
        h.symbol: synthetic_bars(120, seed=hash(h.symbol) % 1000) for h in holdings
    }
    repo = FakeMarketDataRepository(bars_by_symbol=bars_by_symbol)
    data = await fetch_holdings_returns(repo, holdings)
    analytics = AnalyticsService().compute(data)
    risk_metrics = RiskMetricsService().compute(data)
    return data, analytics, risk_metrics, bars_by_symbol


class TestAiPortfolioEngineService:
    async def test_computes_a_full_prediction_set_for_a_multi_holding_portfolio(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech"),
            PortfolioHoldingInput(symbol="MSFT", quantity=5, market_value=500.0, sector="Tech"),
        ]
        data, analytics, risk_metrics, bars_by_symbol = await _build_bundle(holdings)
        service = AiPortfolioEngineService()

        result = service.compute(data, analytics, risk_metrics, bars_by_symbol)

        assert 0.0 <= result.portfolio_risk_prediction <= 100.0
        assert 0.0 <= result.investment_health_prediction <= 100.0
        assert 0.0 <= result.market_exposure_pct <= 100.0
        assert 0.0 <= result.portfolio_stability_score <= 100.0
        assert 0.0 <= result.portfolio_confidence_score <= 100.0
        assert len(result.sector_risk) == 1  # both holdings share "Tech"

    async def test_market_exposure_defaults_to_a_neutral_midpoint_with_no_beta(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data, analytics, risk_metrics, bars_by_symbol = await _build_bundle(holdings)
        service = AiPortfolioEngineService()

        result = service.compute(data, analytics, risk_metrics, bars_by_symbol)

        # No benchmark was supplied to RiskMetricsService.compute() above,
        # so beta is None -> market_exposure_pct must be the disclosed
        # neutral default, not 0 or a misleadingly precise number.
        assert result.market_exposure_pct == 50.0

    async def test_a_holding_missing_from_bars_by_symbol_is_excluded_without_error(self) -> None:
        holdings = [
            PortfolioHoldingInput(symbol="AAPL", quantity=10, market_value=1000.0, sector="Tech")
        ]
        data, analytics, risk_metrics, _ = await _build_bundle(holdings)
        service = AiPortfolioEngineService()

        # Deliberately pass an empty bars_by_symbol — no DecisionEngine
        # call can succeed for any holding.
        result = service.compute(data, analytics, risk_metrics, {})

        assert result.expected_return_pct == 0.0
        assert result.portfolio_confidence_score == 0.0
        assert result.portfolio_stability_score == 0.0

    async def test_empty_holdings_produce_a_well_formed_zeroed_result(self) -> None:
        data, analytics, risk_metrics, bars_by_symbol = await _build_bundle([])
        service = AiPortfolioEngineService()

        result = service.compute(data, analytics, risk_metrics, bars_by_symbol)

        assert result.expected_return_pct == 0.0
        assert result.portfolio_confidence_score == 0.0
        assert result.sector_risk == ()
