"""portfolio_intelligence_router.py — HTTP endpoints for the Phase 10 AI
Portfolio Intelligence feature set (Analytics, Risk Metrics, AI Portfolio
Engine predictions, Modern Portfolio Theory Optimization, AI
Recommendation Engine, Monte Carlo Simulation).

This is the integration step that was missing after the initial ML
verification audit: `PortfolioIntelligenceUseCase`/`MonteCarloUseCase`
(application layer) and the 6 services they orchestrate
(`AnalyticsService`, `RiskMetricsService`, `AiPortfolioEngineService`,
`OptimizationService`, `MonteCarloService`, `RecommendationEngineService`)
already existed, fully implemented and unit-tested — this router is the
first thing that makes them reachable over HTTP, following the EXACT
same pattern ml_router.py already established: build command -> call
use case -> map domain exceptions to HTTP -> return DTO.

Route prefix `/api/v1/portfolio-intelligence` matches the namespace
`apps/core-api/src/application/ai_proxy/ai_service_client.py`'s
`AiServiceClient` Protocol already declared for its 6 Phase 10 methods
(`get_portfolio_analytics`, `get_portfolio_risk_metrics`,
`get_ai_portfolio_predictions`, `run_monte_carlo_simulation`,
`get_portfolio_optimization`, `get_portfolio_recommendations_v2`) —
this router is what finally gives that Protocol's contract something
real to call.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.application.portfolio_intelligence.data import PortfolioHoldingInput
from src.application.portfolio_intelligence.monte_carlo_service import (
    InvalidSimulationRunCountError,
)
from src.application.portfolio_intelligence.optimization_service import OptimizationResult
from src.application.portfolio_intelligence.portfolio_intelligence_use_case import (
    MonteCarloUseCase,
    PortfolioIntelligenceResult,
    PortfolioIntelligenceUseCase,
)
from src.domain.ml.exceptions import MlDomainError
from src.infrastructure.http.market_data_repository import MarketDataUnavailableError
from src.presentation.dependencies.portfolio_intelligence_use_cases import (
    get_monte_carlo_use_case,
    get_portfolio_intelligence_use_case,
)
from src.presentation.dto.portfolio_intelligence_dto import (
    AiPortfolioPredictionsResponse,
    AssetAllocationEntryResponse,
    CapitalAllocationLinePointResponse,
    ConfidenceIntervalResponse,
    CorrelationMatrixResponse,
    DrawdownPointResponse,
    EfficientFrontierPointResponse,
    HistoricalPerformancePointResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    OptimizationResultResponse,
    OptimizedPortfolioResponse,
    PortfolioAnalyticsResponse,
    PortfolioIntelligenceHoldingRequest,
    PortfolioIntelligenceRequest,
    PortfolioIntelligenceResponse,
    RebalancingSuggestionResponse,
    RecommendationResponseItem,
    RiskMetricsResponse,
    SectorExposureEntryResponse,
    SectorRiskEntryResponse,
)
from src.presentation.ml_exception_handlers import raise_ml_exception_as_http

router = APIRouter(prefix="/api/v1/portfolio-intelligence", tags=["portfolio-intelligence"])


def _raise_domain_exception_as_http(exc: Exception) -> None:
    if isinstance(exc, MlDomainError):
        raise_ml_exception_as_http(exc)
    raise exc


def _holdings_from_request(
    holdings: list[PortfolioIntelligenceHoldingRequest],
) -> list[PortfolioHoldingInput]:
    return [
        PortfolioHoldingInput(
            symbol=h.symbol, quantity=h.quantity, market_value=h.market_value, sector=h.sector
        )
        for h in holdings
    ]


def _optimization_to_response(
    optimization: OptimizationResult | None,
) -> OptimizationResultResponse | None:
    if optimization is None:
        return None
    return OptimizationResultResponse(
        symbols=list(optimization.symbols),
        efficient_frontier=[
            EfficientFrontierPointResponse(
                expected_return_pct=p.expected_return_pct,
                volatility_pct=p.volatility_pct,
                weights=list(p.weights),
            )
            for p in optimization.efficient_frontier
        ],
        max_sharpe_portfolio=OptimizedPortfolioResponse(
            weights=list(optimization.max_sharpe_portfolio.weights),
            expected_return_pct=optimization.max_sharpe_portfolio.expected_return_pct,
            volatility_pct=optimization.max_sharpe_portfolio.volatility_pct,
            sharpe_ratio=optimization.max_sharpe_portfolio.sharpe_ratio,
        ),
        min_variance_portfolio=OptimizedPortfolioResponse(
            weights=list(optimization.min_variance_portfolio.weights),
            expected_return_pct=optimization.min_variance_portfolio.expected_return_pct,
            volatility_pct=optimization.min_variance_portfolio.volatility_pct,
            sharpe_ratio=optimization.min_variance_portfolio.sharpe_ratio,
        ),
        capital_allocation_line=[
            CapitalAllocationLinePointResponse(
                volatility_pct=p.volatility_pct, expected_return_pct=p.expected_return_pct
            )
            for p in optimization.capital_allocation_line
        ],
        suggested_rebalancing=[
            RebalancingSuggestionResponse(
                symbol=s.symbol,
                current_weight_pct=s.current_weight_pct,
                suggested_weight_pct=s.suggested_weight_pct,
                delta_pct=s.delta_pct,
            )
            for s in optimization.suggested_rebalancing
        ],
    )


def _result_to_response(result: PortfolioIntelligenceResult) -> PortfolioIntelligenceResponse:
    analytics = result.analytics
    risk_metrics = result.risk_metrics
    ai_predictions = result.ai_predictions

    return PortfolioIntelligenceResponse(
        analytics=PortfolioAnalyticsResponse(
            health_score=analytics.health_score,
            diversification_score=analytics.diversification_score,
            risk_score=analytics.risk_score,
            sector_exposure=[
                SectorExposureEntryResponse(
                    sector=s.sector, market_value=s.market_value, allocation_pct=s.allocation_pct
                )
                for s in analytics.sector_exposure
            ],
            asset_allocation=[
                AssetAllocationEntryResponse(
                    symbol=a.symbol, market_value=a.market_value, allocation_pct=a.allocation_pct
                )
                for a in analytics.asset_allocation
            ],
            concentration_risk=analytics.concentration_risk,
            correlation_matrix=CorrelationMatrixResponse(
                symbols=list(analytics.correlation_matrix.symbols),
                matrix=[list(row) for row in analytics.correlation_matrix.matrix],
            ),
            historical_performance=[
                HistoricalPerformancePointResponse(
                    as_of=p.as_of, portfolio_value_index=p.portfolio_value_index
                )
                for p in analytics.historical_performance
            ],
            daily_return_pct=analytics.daily_return_pct,
            weekly_return_pct=analytics.weekly_return_pct,
            monthly_return_pct=analytics.monthly_return_pct,
            cagr_pct=analytics.cagr_pct,
            annualized_return_pct=analytics.annualized_return_pct,
            annualized_volatility_pct=analytics.annualized_volatility_pct,
        ),
        risk_metrics=RiskMetricsResponse(
            sharpe_ratio=risk_metrics.sharpe_ratio,
            sortino_ratio=risk_metrics.sortino_ratio,
            treynor_ratio=risk_metrics.treynor_ratio,
            alpha_pct=risk_metrics.alpha_pct,
            beta=risk_metrics.beta,
            standard_deviation_pct=risk_metrics.standard_deviation_pct,
            max_drawdown_pct=risk_metrics.max_drawdown_pct,
            drawdown_series=[
                DrawdownPointResponse(as_of=d.as_of, drawdown_pct=d.drawdown_pct)
                for d in risk_metrics.drawdown_series
            ],
            value_at_risk_95_pct=risk_metrics.value_at_risk_95_pct,
            conditional_value_at_risk_95_pct=risk_metrics.conditional_value_at_risk_95_pct,
            expected_shortfall_95_pct=risk_metrics.expected_shortfall_95_pct,
        ),
        ai_predictions=AiPortfolioPredictionsResponse(
            expected_return_pct=ai_predictions.expected_return_pct,
            portfolio_risk_prediction=ai_predictions.portfolio_risk_prediction,
            investment_health_prediction=ai_predictions.investment_health_prediction,
            market_exposure_pct=ai_predictions.market_exposure_pct,
            sector_risk=[
                SectorRiskEntryResponse(sector=s.sector, risk_score=s.risk_score)
                for s in ai_predictions.sector_risk
            ],
            portfolio_stability_score=ai_predictions.portfolio_stability_score,
            portfolio_confidence_score=ai_predictions.portfolio_confidence_score,
        ),
        optimization=_optimization_to_response(result.optimization),
        recommendations=[
            RecommendationResponseItem(
                type=r.type,
                reason=r.reason,
                risk_impact=r.risk_impact,
                expected_improvement=r.expected_improvement,
                confidence=r.confidence,
                affected_assets=list(r.affected_assets),
            )
            for r in result.recommendations
        ],
    )


@router.post("/analyze", response_model=PortfolioIntelligenceResponse)
async def analyze_portfolio(
    body: PortfolioIntelligenceRequest,
    use_case: Annotated[
        PortfolioIntelligenceUseCase, Depends(get_portfolio_intelligence_use_case)
    ],
) -> PortfolioIntelligenceResponse:
    """Runs Analytics, Risk Metrics, the AI Portfolio Engine, MPT
    Optimization, and the AI Recommendation Engine over the supplied
    holdings in one call — the combined response every Phase 10
    quantitative service was originally built to support together."""
    try:
        result = await use_case.execute(
            holdings=_holdings_from_request(body.holdings), lookback_days=body.lookback_days
        )
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return _result_to_response(result)


@router.post("/monte-carlo", response_model=MonteCarloResponse)
async def run_monte_carlo_simulation(
    body: MonteCarloRequest,
    use_case: Annotated[MonteCarloUseCase, Depends(get_monte_carlo_use_case)],
) -> MonteCarloResponse:
    try:
        result = await use_case.execute(
            holdings=_holdings_from_request(body.holdings),
            num_runs=body.num_runs,
            horizon_days=body.horizon_days,
            lookback_days=body.lookback_days,
        )
    except InvalidSimulationRunCountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (MlDomainError, MarketDataUnavailableError) as exc:
        _raise_domain_exception_as_http(exc)
        raise
    return MonteCarloResponse(
        num_runs=result.num_runs,
        horizon_days=result.horizon_days,
        starting_value=result.starting_value,
        confidence_intervals=[
            ConfidenceIntervalResponse(
                day=c.day, p5=c.p5, p25=c.p25, p50=c.p50, p75=c.p75, p95=c.p95
            )
            for c in result.confidence_intervals
        ],
        final_value_distribution=list(result.final_value_distribution),
        worst_case_value=result.worst_case_value,
        expected_case_value=result.expected_case_value,
        best_case_value=result.best_case_value,
    )
