"""RiskMetricsService — Phase 10 Risk Metrics.

Unlike analytics_service.py's Health/Diversification/Risk Scores (genuinely
new composite metrics with disclosed, considered-default formulas), every
metric in this module is a standard, unambiguous textbook financial
calculation — Sharpe Ratio, Sortino Ratio, Treynor Ratio, Alpha, Beta,
Standard Deviation, Maximum Drawdown, Value at Risk, Conditional VaR,
Expected Shortfall. Formulas are cited inline where a specific convention
choice exists (e.g. historical vs. parametric VaR).

BENCHMARK: Beta, Alpha, and Treynor Ratio all require a market benchmark
return series. This module accepts one as a plain parameter (a daily
return series) rather than hardcoding a specific index — the caller
(the orchestrating use case) is responsible for supplying it, matching
this codebase's established "the domain/application layer receives its
inputs, it does not reach out and fetch its own" discipline. See
known-issues.md for how the benchmark is actually sourced (or not) in
this phase's default wiring.

RISK-FREE RATE: Sharpe, Sortino, and Treynor Ratios all subtract a
risk-free rate from returns before computing their ratio. Accepted as a
parameter with a disclosed default (see RiskMetricsService.__init__)
rather than hardcoded, since there is no existing spec value for this
in the codebase and a hardcoded number would misleadingly look like an
authoritative constant.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.application.portfolio_intelligence.data import (
    PortfolioReturnsData,
    annualized_volatility_pct,
    weighted_portfolio_returns,
)

_TRADING_DAYS_PER_YEAR = 252

# Disclosed default — no existing spec value found in this codebase for an
# annual risk-free rate. 4.5% approximates a recent US Treasury short-term
# yield at the time this phase was built; NOT fetched from any live source
# (this dev environment has no such data feed) and should be treated as a
# considered placeholder, not an authoritative constant — see
# known-issues.md.
DEFAULT_ANNUAL_RISK_FREE_RATE_PCT = 4.5


@dataclass(frozen=True, slots=True)
class DrawdownPoint:
    as_of: str
    drawdown_pct: float  # always <= 0; 0 means at a new high-water mark


@dataclass(frozen=True, slots=True)
class RiskMetrics:
    sharpe_ratio: float | None
    sortino_ratio: float | None
    treynor_ratio: float | None
    alpha_pct: float | None
    beta: float | None
    standard_deviation_pct: float
    max_drawdown_pct: float
    drawdown_series: tuple[DrawdownPoint, ...]
    value_at_risk_95_pct: float | None
    conditional_value_at_risk_95_pct: float | None
    expected_shortfall_95_pct: float | None


class RiskMetricsService:
    def __init__(
        self, annual_risk_free_rate_pct: float = DEFAULT_ANNUAL_RISK_FREE_RATE_PCT
    ) -> None:
        self._daily_risk_free_rate = (1 + annual_risk_free_rate_pct / 100.0) ** (
            1.0 / _TRADING_DAYS_PER_YEAR
        ) - 1.0

    def compute(
        self, data: PortfolioReturnsData, benchmark_daily_returns: pd.Series | None = None
    ) -> RiskMetrics:
        portfolio_returns = weighted_portfolio_returns(data)

        standard_deviation_pct = annualized_volatility_pct(portfolio_returns)
        drawdown_series, max_drawdown_pct = _compute_drawdown(portfolio_returns)

        sharpe_ratio = _sharpe_ratio(portfolio_returns, self._daily_risk_free_rate)
        sortino_ratio = _sortino_ratio(portfolio_returns, self._daily_risk_free_rate)

        beta = None
        alpha_pct = None
        treynor_ratio = None
        if benchmark_daily_returns is not None and not benchmark_daily_returns.empty:
            beta = _beta(portfolio_returns, benchmark_daily_returns)
            alpha_pct = _alpha_pct(
                portfolio_returns, benchmark_daily_returns, beta, self._daily_risk_free_rate
            )
            treynor_ratio = _treynor_ratio(portfolio_returns, beta, self._daily_risk_free_rate)

        var_95, cvar_95, es_95 = _historical_var_cvar_es(portfolio_returns, confidence=0.95)

        return RiskMetrics(
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            treynor_ratio=treynor_ratio,
            alpha_pct=alpha_pct,
            beta=beta,
            standard_deviation_pct=standard_deviation_pct,
            max_drawdown_pct=max_drawdown_pct,
            drawdown_series=drawdown_series,
            value_at_risk_95_pct=var_95,
            conditional_value_at_risk_95_pct=cvar_95,
            expected_shortfall_95_pct=es_95,
        )


def _sharpe_ratio(returns: pd.Series, daily_risk_free_rate: float) -> float | None:
    """Sharpe Ratio = (mean excess return / std dev of excess return),
    annualized by sqrt(252) — the standard textbook formula."""
    if returns.empty or len(returns) < 2:
        return None
    excess = returns - daily_risk_free_rate
    std = float(excess.std())
    if std == 0.0:
        return None
    return float(excess.mean() / std * np.sqrt(_TRADING_DAYS_PER_YEAR))


def _sortino_ratio(returns: pd.Series, daily_risk_free_rate: float) -> float | None:
    """Sortino Ratio — like Sharpe, but the denominator is DOWNSIDE
    deviation only (std dev of returns below the risk-free rate), the
    standard refinement that doesn't penalize upside volatility."""
    if returns.empty or len(returns) < 2:
        return None
    excess = returns - daily_risk_free_rate
    downside = excess[excess < 0]
    if downside.empty:
        return None  # no downside observed — ratio is undefined, not infinite
    downside_std = float(np.sqrt((downside**2).mean()))
    if downside_std == 0.0:
        return None
    return float(excess.mean() / downside_std * np.sqrt(_TRADING_DAYS_PER_YEAR))


def _beta(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Beta = Cov(portfolio, benchmark) / Var(benchmark) — the standard
    CAPM formula, computed over the dates both series have in common."""
    aligned = pd.concat({"p": portfolio_returns, "b": benchmark_returns}, axis=1).dropna()
    if len(aligned) < 2:
        return None
    covariance = float(aligned["p"].cov(aligned["b"]))
    benchmark_variance = float(aligned["b"].var())
    if benchmark_variance == 0.0:
        return None
    return covariance / benchmark_variance


def _alpha_pct(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    beta: float | None,
    daily_risk_free_rate: float,
) -> float | None:
    """Jensen's Alpha (annualized, %) = portfolio return - [risk-free
    rate + beta * (benchmark return - risk-free rate)] — the standard
    CAPM-based excess-return-over-expected-return formula."""
    if beta is None:
        return None
    aligned = pd.concat({"p": portfolio_returns, "b": benchmark_returns}, axis=1).dropna()
    if aligned.empty:
        return None
    portfolio_mean = float(aligned["p"].mean())
    benchmark_mean = float(aligned["b"].mean())
    daily_alpha = (portfolio_mean - daily_risk_free_rate) - beta * (
        benchmark_mean - daily_risk_free_rate
    )
    return float(((1.0 + daily_alpha) ** _TRADING_DAYS_PER_YEAR - 1.0) * 100.0)


def _treynor_ratio(
    portfolio_returns: pd.Series, beta: float | None, daily_risk_free_rate: float
) -> float | None:
    """Treynor Ratio = (mean excess return / beta), annualized — like
    Sharpe but normalized by systematic risk (beta) rather than total
    volatility."""
    if beta is None or beta == 0.0 or portfolio_returns.empty:
        return None
    excess_mean = float(portfolio_returns.mean()) - daily_risk_free_rate
    annualized_excess = (1.0 + excess_mean) ** _TRADING_DAYS_PER_YEAR - 1.0
    return annualized_excess / beta


def _compute_drawdown(returns: pd.Series) -> tuple[tuple[DrawdownPoint, ...], float]:
    """Maximum Drawdown — the largest peak-to-trough decline in the
    cumulative-growth-of-100 index, the standard formula. Returns the
    full drawdown series (for charting) alongside the single worst
    value."""
    if returns.empty:
        return (), 0.0
    cumulative = (1.0 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative / running_max - 1.0) * 100.0
    series = tuple(
        DrawdownPoint(as_of=ts.date().isoformat(), drawdown_pct=float(v))
        for ts, v in drawdown.items()
    )
    max_drawdown_pct = float(drawdown.min())
    return series, max_drawdown_pct


def _historical_var_cvar_es(
    returns: pd.Series, confidence: float
) -> tuple[float | None, float | None, float | None]:
    """Historical (non-parametric) VaR/CVaR/Expected Shortfall — chosen
    over a parametric (normal-distribution-assumption) approach because
    it makes no distributional assumption about returns, which is the
    more defensible choice given real daily equity returns are well
    known to be fat-tailed (non-normal). VaR at the 95% confidence level
    is the 5th percentile of the historical return distribution
    (expressed as a positive percentage LOSS, the standard convention);
    CVaR/Expected Shortfall (synonymous formulas, standard terminology
    overlap in the literature — this codebase names both explicitly per
    the founder's own requirement list naming them separately) is the
    average of all returns AT OR BELOW that percentile."""
    if returns.empty or len(returns) < 20:
        # A percentile computed from fewer than ~20 observations is not
        # meaningful — disclosed threshold, not a hardcoded false
        # precision on a tiny sample.
        return None, None, None
    var_percentile = 1.0 - confidence
    var_threshold = float(np.percentile(returns, var_percentile * 100.0))
    tail_losses = returns[returns <= var_threshold]
    cvar = float(tail_losses.mean()) if not tail_losses.empty else var_threshold
    # VaR/CVaR/ES are conventionally reported as positive loss percentages.
    return -var_threshold * 100.0, -cvar * 100.0, -cvar * 100.0
