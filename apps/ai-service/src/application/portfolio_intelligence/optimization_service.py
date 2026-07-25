"""OptimizationService — Phase 10 Portfolio Optimization (Modern
Portfolio Theory).

Implements: Efficient Frontier, Maximum Sharpe Portfolio, Minimum
Variance Portfolio, Capital Allocation Line, Suggested Rebalancing.

METHOD: scipy.optimize.minimize (SLSQP, the standard choice for
constrained nonlinear optimization with equality/inequality constraints)
— confirmed available transitively via this codebase's existing
dependency tree (statsmodels/scikit-learn both depend on scipy; no new
dependency was added). Every optimization in this module shares the
SAME constraint set: weights must sum to 1 (fully invested, no cash
drag) and every weight must be >= 0 — LONG-ONLY. This is not just a
simplification for convenience: this codebase's own Portfolio domain
model (Holding, Phase 3) has no concept of a negative/short position at
all, so allowing negative optimized weights would produce a
recommendation this platform's own domain model cannot actually
represent as a real holding.

RISK-FREE RATE: reuses risk_metrics_service.py's own
DEFAULT_ANNUAL_RISK_FREE_RATE_PCT constant (imported, not redefined) for
both the Maximum Sharpe optimization objective and the Capital
Allocation Line's risk-free intercept — the same disclosed placeholder
value, one single source of truth.

SUGGESTED REBALANCING: compares the portfolio's CURRENT weights against
the Maximum Sharpe portfolio's optimized weights, producing a per-
holding delta. This is a DATA output (weight deltas) — the AI
Recommendation Engine (Task 8) is what layers human-readable reasoning
and explainability on top of this output, rather than this module
duplicating that reasoning itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.application.portfolio_intelligence.data import PortfolioReturnsData
from src.application.portfolio_intelligence.risk_metrics_service import (
    DEFAULT_ANNUAL_RISK_FREE_RATE_PCT,
)

_TRADING_DAYS_PER_YEAR = 252
_EFFICIENT_FRONTIER_POINTS = 25

FloatArray = np.ndarray[tuple[int, ...], np.dtype[np.float64]]


@dataclass(frozen=True, slots=True)
class EfficientFrontierPoint:
    expected_return_pct: float
    volatility_pct: float
    weights: tuple[float, ...]  # same order as OptimizationResult.symbols


@dataclass(frozen=True, slots=True)
class OptimizedPortfolio:
    weights: tuple[float, ...]  # same order as OptimizationResult.symbols
    expected_return_pct: float
    volatility_pct: float
    sharpe_ratio: float


@dataclass(frozen=True, slots=True)
class CapitalAllocationLinePoint:
    volatility_pct: float
    expected_return_pct: float


@dataclass(frozen=True, slots=True)
class RebalancingSuggestion:
    symbol: str
    current_weight_pct: float
    suggested_weight_pct: float
    delta_pct: float  # positive = suggest increasing, negative = suggest decreasing


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    symbols: tuple[str, ...]
    efficient_frontier: tuple[EfficientFrontierPoint, ...]
    max_sharpe_portfolio: OptimizedPortfolio
    min_variance_portfolio: OptimizedPortfolio
    capital_allocation_line: tuple[CapitalAllocationLinePoint, CapitalAllocationLinePoint]
    """Exactly 2 points — the risk-free intercept (0 volatility) and the
    tangency point at the Max Sharpe portfolio — sufficient to draw the
    line; not itself an optimization, just these 2 points."""
    suggested_rebalancing: tuple[RebalancingSuggestion, ...]


class InsufficientHoldingsForOptimizationError(ValueError):
    """Raised when there are fewer than 2 holdings with return data —
    portfolio optimization (choosing weights ACROSS holdings) is
    undefined for 0 or 1 holdings; a single-holding "portfolio" has
    only one possible weighting (100%), so there is nothing to
    optimize."""


class OptimizationService:
    def __init__(
        self, annual_risk_free_rate_pct: float = DEFAULT_ANNUAL_RISK_FREE_RATE_PCT
    ) -> None:
        self._risk_free_rate_pct = annual_risk_free_rate_pct

    def optimize(self, data: PortfolioReturnsData) -> OptimizationResult:
        if len(data.holdings) < 2:
            raise InsufficientHoldingsForOptimizationError(
                "Portfolio optimization requires at least 2 holdings with return data"
            )

        symbols = tuple(h.symbol for h in data.holdings)
        aligned_returns = pd.concat(
            {h.symbol: h.daily_returns for h in data.holdings}, axis=1
        ).fillna(0.0)
        mean_daily_returns = aligned_returns.mean().to_numpy()
        covariance_matrix = aligned_returns.cov().to_numpy()

        current_weights = tuple(h.weight for h in data.holdings)

        min_variance_weights = _minimize_variance(covariance_matrix)
        max_sharpe_weights = _maximize_sharpe(
            mean_daily_returns, covariance_matrix, self._risk_free_rate_pct
        )

        min_variance_portfolio = _build_optimized_portfolio(
            min_variance_weights, mean_daily_returns, covariance_matrix, self._risk_free_rate_pct
        )
        max_sharpe_portfolio = _build_optimized_portfolio(
            max_sharpe_weights, mean_daily_returns, covariance_matrix, self._risk_free_rate_pct
        )

        efficient_frontier = _build_efficient_frontier(
            mean_daily_returns,
            covariance_matrix,
            min_variance_portfolio.expected_return_pct,
        )

        capital_allocation_line = (
            CapitalAllocationLinePoint(
                volatility_pct=0.0, expected_return_pct=self._risk_free_rate_pct
            ),
            CapitalAllocationLinePoint(
                volatility_pct=max_sharpe_portfolio.volatility_pct,
                expected_return_pct=max_sharpe_portfolio.expected_return_pct,
            ),
        )

        suggested_rebalancing = tuple(
            RebalancingSuggestion(
                symbol=symbol,
                current_weight_pct=current_weights[i] * 100.0,
                suggested_weight_pct=max_sharpe_weights[i] * 100.0,
                delta_pct=(max_sharpe_weights[i] - current_weights[i]) * 100.0,
            )
            for i, symbol in enumerate(symbols)
        )

        return OptimizationResult(
            symbols=symbols,
            efficient_frontier=efficient_frontier,
            max_sharpe_portfolio=max_sharpe_portfolio,
            min_variance_portfolio=min_variance_portfolio,
            capital_allocation_line=capital_allocation_line,
            suggested_rebalancing=suggested_rebalancing,
        )


def _portfolio_return_and_volatility(
    weights: FloatArray, mean_daily_returns: FloatArray, covariance_matrix: FloatArray
) -> tuple[float, float]:
    daily_return = float(np.dot(weights, mean_daily_returns))
    annualized_return_pct = ((1.0 + daily_return) ** _TRADING_DAYS_PER_YEAR - 1.0) * 100.0
    daily_variance = float(np.dot(weights, np.dot(covariance_matrix, weights)))
    annualized_volatility_pct = float(np.sqrt(max(daily_variance, 0.0))) * float(
        np.sqrt(_TRADING_DAYS_PER_YEAR)
    ) * 100.0
    return annualized_return_pct, annualized_volatility_pct


def _build_optimized_portfolio(
    weights: FloatArray,
    mean_daily_returns: FloatArray,
    covariance_matrix: FloatArray,
    risk_free_rate_pct: float,
) -> OptimizedPortfolio:
    expected_return_pct, volatility_pct = _portfolio_return_and_volatility(
        weights, mean_daily_returns, covariance_matrix
    )
    sharpe_ratio = (
        (expected_return_pct - risk_free_rate_pct) / volatility_pct if volatility_pct > 0 else 0.0
    )
    return OptimizedPortfolio(
        weights=tuple(float(w) for w in weights),
        expected_return_pct=expected_return_pct,
        volatility_pct=volatility_pct,
        sharpe_ratio=sharpe_ratio,
    )


def _long_only_fully_invested_constraints(n: int) -> tuple[dict[str, object], ...]:
    return ({"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},)


def _minimize_variance(covariance_matrix: FloatArray) -> FloatArray:
    n = covariance_matrix.shape[0]
    initial_guess = np.full(n, 1.0 / n)
    bounds = tuple((0.0, 1.0) for _ in range(n))

    def objective(weights: FloatArray) -> float:
        return float(np.dot(weights, np.dot(covariance_matrix, weights)))

    result = minimize(
        objective,
        initial_guess,
        method="SLSQP",
        bounds=bounds,
        constraints=_long_only_fully_invested_constraints(n),
    )
    return np.asarray(result.x) if result.success else initial_guess


def _maximize_sharpe(
    mean_daily_returns: FloatArray, covariance_matrix: FloatArray, risk_free_rate_pct: float
) -> FloatArray:
    n = mean_daily_returns.shape[0]
    initial_guess = np.full(n, 1.0 / n)
    bounds = tuple((0.0, 1.0) for _ in range(n))

    def negative_sharpe(weights: FloatArray) -> float:
        expected_return_pct, volatility_pct = _portfolio_return_and_volatility(
            weights, mean_daily_returns, covariance_matrix
        )
        if volatility_pct <= 0:
            return 0.0
        return -(expected_return_pct - risk_free_rate_pct) / volatility_pct

    result = minimize(
        negative_sharpe,
        initial_guess,
        method="SLSQP",
        bounds=bounds,
        constraints=_long_only_fully_invested_constraints(n),
    )
    return np.asarray(result.x) if result.success else initial_guess


def _build_efficient_frontier(
    mean_daily_returns: FloatArray,
    covariance_matrix: FloatArray,
    min_variance_return_pct: float,
) -> tuple[EfficientFrontierPoint, ...]:
    """Minimizes variance for each of a series of target returns spanning
    from the Minimum Variance portfolio's own return up to the single
    highest-returning individual holding's own annualized return (the
    achievable maximum for a long-only, fully-invested portfolio) —
    the standard "trace out the frontier" construction."""
    n = mean_daily_returns.shape[0]
    bounds = tuple((0.0, 1.0) for _ in range(n))
    per_asset_annualized_returns = (
        (1.0 + mean_daily_returns) ** _TRADING_DAYS_PER_YEAR - 1.0
    ) * 100.0
    max_achievable_return_pct = float(np.max(per_asset_annualized_returns))

    if max_achievable_return_pct <= min_variance_return_pct:
        max_achievable_return_pct = min_variance_return_pct + 1.0

    target_returns = np.linspace(
        min_variance_return_pct, max_achievable_return_pct, _EFFICIENT_FRONTIER_POINTS
    )

    points: list[EfficientFrontierPoint] = []
    for target_return_pct in target_returns:
        initial_guess = np.full(n, 1.0 / n)

        def variance_objective(weights: FloatArray) -> float:
            return float(np.dot(weights, np.dot(covariance_matrix, weights)))

        def return_constraint(
            weights: FloatArray, target: float = float(target_return_pct)
        ) -> float:
            achieved_return_pct, _ = _portfolio_return_and_volatility(
                weights, mean_daily_returns, covariance_matrix
            )
            return achieved_return_pct - target

        constraints = (
            *_long_only_fully_invested_constraints(n),
            {"type": "eq", "fun": return_constraint},
        )
        result = minimize(
            variance_objective,
            initial_guess,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )
        if not result.success:
            continue
        weights = np.asarray(result.x)
        achieved_return_pct, achieved_volatility_pct = _portfolio_return_and_volatility(
            weights, mean_daily_returns, covariance_matrix
        )
        points.append(
            EfficientFrontierPoint(
                expected_return_pct=achieved_return_pct,
                volatility_pct=achieved_volatility_pct,
                weights=tuple(float(w) for w in weights),
            )
        )
    return tuple(points)
