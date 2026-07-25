"""AnalyticsService — Phase 10 Portfolio Analytics.

Computes: Health Score, Diversification Score, Risk Score, Sector
Exposure, Asset Allocation, Concentration Risk, Correlation Matrix,
Historical Performance, Daily/Weekly/Monthly Returns, CAGR, Annualized
Return, Annualized Volatility — all from the shared
`PortfolioReturnsData` (see data.py) that every Phase 10 quantitative
use case builds on.

SCORING FORMULAS — DISCLOSED, NOT AN AUTHORITATIVE INDUSTRY STANDARD:
no existing spec in this codebase defines the exact composition of a
0-100 "Health Score," "Diversification Score," or "Risk Score" — these
are genuinely new composite metrics, not a pre-existing calculation
this task is merely wiring up (unlike, say, Sharpe Ratio, which has one
unambiguous textbook formula — see risk_metrics.py). Matching this
codebase's established "disclose a considered default rather than
fabricate a fake authoritative source" precedent (e.g. Phase 9's
WebSocket backoff intervals, toast auto-dismiss timeout), the exact
formulas are documented inline at each function below, so a future
phase can deliberately revise them with full visibility into what they
originally were and why.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.application.portfolio_intelligence.data import (
    PortfolioReturnsData,
    weighted_portfolio_returns,
)
from src.application.portfolio_intelligence.data import (
    annualized_volatility_pct as _shared_annualized_volatility_pct,
)

_TRADING_DAYS_PER_YEAR = 252
_TRADING_DAYS_PER_WEEK = 5
_TRADING_DAYS_PER_MONTH = 21


@dataclass(frozen=True, slots=True)
class SectorExposureEntry:
    sector: str
    market_value: float
    allocation_pct: float


@dataclass(frozen=True, slots=True)
class AssetAllocationEntry:
    symbol: str
    market_value: float
    allocation_pct: float


@dataclass(frozen=True, slots=True)
class CorrelationMatrix:
    symbols: tuple[str, ...]
    # Row-major — matrix[i][j] is the correlation between symbols[i] and
    # symbols[j]. A flat list-of-lists (not a dict-of-dicts) since every
    # consumer (JSON API response, frontend heatmap) wants a dense grid.
    matrix: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class HistoricalPerformancePoint:
    as_of: str  # ISO date
    portfolio_value_index: float  # normalized to 100 at the start of the lookback window


@dataclass(frozen=True, slots=True)
class PortfolioAnalytics:
    health_score: float
    diversification_score: float
    risk_score: float
    sector_exposure: tuple[SectorExposureEntry, ...]
    asset_allocation: tuple[AssetAllocationEntry, ...]
    concentration_risk: float  # Herfindahl-Hirschman Index, 0 (diversified) to 1 (single holding)
    correlation_matrix: CorrelationMatrix
    historical_performance: tuple[HistoricalPerformancePoint, ...]
    daily_return_pct: float | None
    weekly_return_pct: float | None
    monthly_return_pct: float | None
    cagr_pct: float | None
    annualized_return_pct: float
    annualized_volatility_pct: float


class AnalyticsService:
    def compute(self, data: PortfolioReturnsData) -> PortfolioAnalytics:
        weights = np.array([h.weight for h in data.holdings], dtype=np.float64)
        portfolio_daily_returns = weighted_portfolio_returns(data)

        sector_exposure = _compute_sector_exposure(data)
        asset_allocation = _compute_asset_allocation(data)
        concentration_risk = _herfindahl_index(weights)
        correlation_matrix = _compute_correlation_matrix(data)
        historical_performance = _compute_historical_performance(portfolio_daily_returns)

        annualized_return_pct = _annualized_return_pct(portfolio_daily_returns)
        annualized_volatility_pct = _shared_annualized_volatility_pct(portfolio_daily_returns)
        cagr_pct = _cagr_pct(portfolio_daily_returns)
        daily_return_pct = _period_return_pct(portfolio_daily_returns, periods=1)
        weekly_return_pct = _period_return_pct(
            portfolio_daily_returns, periods=_TRADING_DAYS_PER_WEEK
        )
        monthly_return_pct = _period_return_pct(
            portfolio_daily_returns, periods=_TRADING_DAYS_PER_MONTH
        )

        diversification_score = _diversification_score(
            concentration_risk, num_sectors=len({h.sector for h in data.holdings if h.sector})
        )
        risk_score = _risk_score(annualized_volatility_pct, concentration_risk)
        health_score = _health_score(diversification_score, risk_score, annualized_return_pct)

        return PortfolioAnalytics(
            health_score=health_score,
            diversification_score=diversification_score,
            risk_score=risk_score,
            sector_exposure=sector_exposure,
            asset_allocation=asset_allocation,
            concentration_risk=concentration_risk,
            correlation_matrix=correlation_matrix,
            historical_performance=historical_performance,
            daily_return_pct=daily_return_pct,
            weekly_return_pct=weekly_return_pct,
            monthly_return_pct=monthly_return_pct,
            cagr_pct=cagr_pct,
            annualized_return_pct=annualized_return_pct,
            annualized_volatility_pct=annualized_volatility_pct,
        )


def _compute_sector_exposure(data: PortfolioReturnsData) -> tuple[SectorExposureEntry, ...]:
    totals: dict[str, float] = {}
    for holding in data.holdings:
        sector = holding.sector or "Unknown"
        totals[sector] = totals.get(sector, 0.0) + (holding.weight * data.total_market_value)
    total = sum(totals.values())
    return tuple(
        SectorExposureEntry(
            sector=sector,
            market_value=value,
            allocation_pct=(value / total * 100.0) if total > 0 else 0.0,
        )
        for sector, value in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    )


def _compute_asset_allocation(data: PortfolioReturnsData) -> tuple[AssetAllocationEntry, ...]:
    return tuple(
        AssetAllocationEntry(
            symbol=h.symbol,
            market_value=h.weight * data.total_market_value,
            allocation_pct=h.weight * 100.0,
        )
        for h in sorted(data.holdings, key=lambda h: h.weight, reverse=True)
    )


def _herfindahl_index(weights: np.ndarray[tuple[int], np.dtype[np.float64]]) -> float:
    """Concentration Risk — the standard Herfindahl-Hirschman Index
    (sum of squared weights), a genuine, unambiguous textbook formula
    (not a disclosed-default composite like health/diversification/risk
    scores below) — 1.0 for a single-holding portfolio, approaching 0
    as holdings become more numerous and evenly weighted."""
    if weights.size == 0:
        return 0.0
    return float(np.sum(weights**2))


def _compute_correlation_matrix(data: PortfolioReturnsData) -> CorrelationMatrix:
    if len(data.holdings) < 2:
        symbols = tuple(h.symbol for h in data.holdings)
        # A single holding's "correlation matrix" is just [[1.0]] — not
        # undefined, since a series is always perfectly correlated with
        # itself; zero holdings is an empty matrix.
        matrix: tuple[tuple[float, ...], ...] = ((1.0,),) if symbols else ()
        return CorrelationMatrix(symbols=symbols, matrix=matrix)
    aligned = pd.concat({h.symbol: h.daily_returns for h in data.holdings}, axis=1).fillna(0.0)
    corr = aligned.corr()
    symbols = tuple(corr.columns)
    matrix = tuple(tuple(float(v) for v in row) for row in corr.to_numpy())
    return CorrelationMatrix(symbols=symbols, matrix=matrix)


def _compute_historical_performance(
    portfolio_daily_returns: pd.Series,
) -> tuple[HistoricalPerformancePoint, ...]:
    """An index series starting at 100 on the first day of the lookback
    window, compounding the portfolio's own weighted daily returns —
    the standard "growth of 100" performance-chart convention, chosen
    because this codebase has no historical per-day PORTFOLIO VALUE
    record to plot directly (only current holdings + current market
    value), matching the same returns-based approximation
    `_weighted_portfolio_returns` already discloses above."""
    if portfolio_daily_returns.empty:
        return ()
    index_series = (1.0 + portfolio_daily_returns).cumprod() * 100.0
    return tuple(
        HistoricalPerformancePoint(as_of=ts.date().isoformat(), portfolio_value_index=float(v))
        for ts, v in index_series.items()
    )


def _annualized_return_pct(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    mean_daily = float(returns.mean())
    return ((1.0 + mean_daily) ** _TRADING_DAYS_PER_YEAR - 1.0) * 100.0


def _cagr_pct(returns: pd.Series) -> float | None:
    """Compound Annual Growth Rate over the actual observed lookback
    window (not assumed to be exactly 1 year) — None if there isn't at
    least 2 trading days of history to compound over."""
    if returns.empty or len(returns) < 2:
        return None
    cumulative_growth = float((1.0 + returns).prod())
    years = len(returns) / _TRADING_DAYS_PER_YEAR
    if years <= 0 or cumulative_growth <= 0:
        return None
    return float((cumulative_growth ** (1.0 / years) - 1.0) * 100.0)


def _period_return_pct(returns: pd.Series, periods: int) -> float | None:
    """The actual compounded return over the most recent `periods`
    trading days — None if there isn't enough history for that window
    yet (e.g. a portfolio younger than a week has no weekly_return_pct)."""
    if len(returns) < periods:
        return None
    recent = returns.iloc[-periods:]
    return float(float((1.0 + recent).prod()) * 100.0 - 100.0)


def _diversification_score(concentration_risk: float, num_sectors: int) -> float:
    """DISCLOSED DEFAULT FORMULA (see module docstring) — 0-100, blending
    two considerations: (1) how concentrated the portfolio is by weight
    (via 1 - HHI, so a maximally spread portfolio scores near 100 on
    this component) and (2) how many distinct sectors are represented
    (capped contribution at 5+ sectors, since diminishing marginal
    diversification benefit beyond that is a standard portfolio-theory
    intuition, not a fabricated number pretending otherwise). Weighted
    70/30 toward the weight-concentration component since that is the
    more directly measurable, less debatable half of "diversification."
    """
    weight_component = (1.0 - concentration_risk) * 100.0
    sector_component = min(num_sectors, 5) / 5.0 * 100.0
    return round(weight_component * 0.7 + sector_component * 0.3, 2)


def _risk_score(annualized_volatility_pct: float, concentration_risk: float) -> float:
    """DISCLOSED DEFAULT FORMULA — 0-100, HIGHER = RISKIER (i.e. this is
    not inverted into a "safety score"). Blends annualized volatility
    (capped at 60% for scoring purposes — a 60%+ annualized-volatility
    single-stock-like portfolio is treated as maximally risky on this
    axis, rather than letting one extreme outlier holding produce an
    unbounded score) with concentration risk (a concentrated portfolio
    is inherently riskier independent of its historical volatility,
    since a single bad idiosyncratic event has outsized impact)."""
    volatility_component = min(annualized_volatility_pct, 60.0) / 60.0 * 100.0
    concentration_component = concentration_risk * 100.0
    return round(volatility_component * 0.6 + concentration_component * 0.4, 2)


def _health_score(
    diversification_score: float, risk_score: float, annualized_return_pct: float
) -> float:
    """DISCLOSED DEFAULT FORMULA — 0-100, HIGHER = HEALTHIER. Combines
    diversification (good), inverted risk (less risk = healthier), and
    a bounded reward for positive annualized return (capped at +30%,
    floored at -30%, so a single extreme return doesn't dominate the
    score in either direction) — an intentionally simple three-factor
    blend rather than a more elaborate model, since no existing spec
    defines what "portfolio health" should weigh."""
    risk_component = 100.0 - risk_score
    return_component = (max(min(annualized_return_pct, 30.0), -30.0) + 30.0) / 60.0 * 100.0
    return round(
        diversification_score * 0.4 + risk_component * 0.4 + return_component * 0.2, 2
    )
