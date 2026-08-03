"""Pydantic request/response DTOs for the Phase 10 Portfolio Intelligence
REST API (`/api/v1/portfolio-intelligence/*`) — mirrors ml_dto.py's own
conventions (plain float fields, no decimal-as-string since these are
statistical/percentage figures rather than money amounts, matching
analytics_service.py/risk_metrics_service.py's own dataclass field types
exactly). One response field per source dataclass field — no renaming,
so the wire shape is traceable 1:1 back to the domain dataclasses in
src/application/portfolio_intelligence/.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioIntelligenceHoldingRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)
    market_value: float = Field(..., gt=0)
    sector: str | None = None


class PortfolioIntelligenceRequest(BaseModel):
    holdings: list[PortfolioIntelligenceHoldingRequest] = Field(..., min_length=1)
    lookback_days: int = Field(default=400, ge=30, le=2000)


# --- Analytics ---


class SectorExposureEntryResponse(BaseModel):
    sector: str
    market_value: float
    allocation_pct: float


class AssetAllocationEntryResponse(BaseModel):
    symbol: str
    market_value: float
    allocation_pct: float


class CorrelationMatrixResponse(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]


class HistoricalPerformancePointResponse(BaseModel):
    as_of: str
    portfolio_value_index: float


class PortfolioAnalyticsResponse(BaseModel):
    health_score: float
    diversification_score: float
    risk_score: float
    sector_exposure: list[SectorExposureEntryResponse]
    asset_allocation: list[AssetAllocationEntryResponse]
    concentration_risk: float
    correlation_matrix: CorrelationMatrixResponse
    historical_performance: list[HistoricalPerformancePointResponse]
    daily_return_pct: float | None
    weekly_return_pct: float | None
    monthly_return_pct: float | None
    cagr_pct: float | None
    annualized_return_pct: float
    annualized_volatility_pct: float


# --- Risk Metrics ---


class DrawdownPointResponse(BaseModel):
    as_of: str
    drawdown_pct: float


class RiskMetricsResponse(BaseModel):
    sharpe_ratio: float | None
    sortino_ratio: float | None
    treynor_ratio: float | None
    alpha_pct: float | None
    beta: float | None
    standard_deviation_pct: float
    max_drawdown_pct: float
    drawdown_series: list[DrawdownPointResponse]
    value_at_risk_95_pct: float | None
    conditional_value_at_risk_95_pct: float | None
    expected_shortfall_95_pct: float | None


# --- AI Portfolio Engine predictions ---


class SectorRiskEntryResponse(BaseModel):
    sector: str
    risk_score: float


class AiPortfolioPredictionsResponse(BaseModel):
    expected_return_pct: float
    portfolio_risk_prediction: float
    investment_health_prediction: float
    market_exposure_pct: float
    sector_risk: list[SectorRiskEntryResponse]
    portfolio_stability_score: float
    portfolio_confidence_score: float


# --- Optimization ---


class EfficientFrontierPointResponse(BaseModel):
    expected_return_pct: float
    volatility_pct: float
    weights: list[float]


class OptimizedPortfolioResponse(BaseModel):
    weights: list[float]
    expected_return_pct: float
    volatility_pct: float
    sharpe_ratio: float


class CapitalAllocationLinePointResponse(BaseModel):
    volatility_pct: float
    expected_return_pct: float


class RebalancingSuggestionResponse(BaseModel):
    symbol: str
    current_weight_pct: float
    suggested_weight_pct: float
    delta_pct: float


class OptimizationResultResponse(BaseModel):
    symbols: list[str]
    efficient_frontier: list[EfficientFrontierPointResponse]
    max_sharpe_portfolio: OptimizedPortfolioResponse
    min_variance_portfolio: OptimizedPortfolioResponse
    capital_allocation_line: list[CapitalAllocationLinePointResponse]
    suggested_rebalancing: list[RebalancingSuggestionResponse]


# --- Recommendations ---


class RecommendationResponseItem(BaseModel):
    type: str
    reason: str
    risk_impact: str
    expected_improvement: str
    confidence: float
    affected_assets: list[str]


# --- Combined response ---


class PortfolioIntelligenceResponse(BaseModel):
    analytics: PortfolioAnalyticsResponse
    risk_metrics: RiskMetricsResponse
    ai_predictions: AiPortfolioPredictionsResponse
    optimization: OptimizationResultResponse | None
    """None when the portfolio has fewer than 2 holdings with usable
    return data — optimization is mathematically undefined in that case
    (see OptimizationService.optimize()'s
    InsufficientHoldingsForOptimizationError), not an error condition."""
    recommendations: list[RecommendationResponseItem]


# --- Monte Carlo ---


class MonteCarloRequest(BaseModel):
    holdings: list[PortfolioIntelligenceHoldingRequest] = Field(..., min_length=1)
    num_runs: int = Field(..., description="Must be one of 100, 500, 1000, 5000")
    horizon_days: int = Field(default=252, ge=1, le=2520)
    lookback_days: int = Field(default=400, ge=30, le=2000)


class ConfidenceIntervalResponse(BaseModel):
    day: int
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


class MonteCarloResponse(BaseModel):
    num_runs: int
    horizon_days: int
    starting_value: float
    confidence_intervals: list[ConfidenceIntervalResponse]
    final_value_distribution: list[float]
    worst_case_value: float
    expected_case_value: float
    best_case_value: float
