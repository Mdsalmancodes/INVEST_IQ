"""portfolio_intelligence — Phase 10 (AI Portfolio Intelligence).

A new, additive application-layer module hosting ALL quantitative
portfolio computation for Phase 10: analytics scores, risk metrics, the
AI Portfolio Engine, Monte Carlo simulation, Modern Portfolio Theory
optimization, and the AI Recommendation Engine. Placed in ai-service
(not core-api) because ai-service is the ONLY service in this monorepo
with numpy/pandas/scipy available (confirmed by reading core-api's
pyproject.toml — it has none of these) — this directly extends the
exact bounded-context split Phase 7 already established (ai-service
does all numerical/statistical work; core-api does business logic,
persistence, and orchestration), not a new architectural pattern.

This module's use cases accept a plain list of (symbol, quantity,
market_value) holdings as direct input, exactly mirroring the EXISTING
Phase 7 `portfolio_recommendation_use_case.py`'s own established
pattern (PortfolioHolding(symbol, quantity)) — core-api's own
authenticated Portfolio module (PortfolioRepository +
PortfolioCalculationService, both frozen and unmodified) is what
actually loads a user's real holdings; this module never touches
core-api's Postgres or has any concept of a user session.

DATA FLOW: historical OHLCV bars for every holding symbol are fetched
via the EXISTING `MarketDataRepository` Protocol (Phase 7,
`HttpMarketDataRepository` — an HTTP call to core-api's PUBLIC
`GET /api/v1/instruments/{symbol}/bars` endpoint). This module never
duplicates that data or opens a second HTTP client — see
`fetch_holdings_returns()` below, the single shared helper every Phase
10 use case that needs historical returns calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.domain.ml.repositories import MarketDataRepository, OhlcvBar

_TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class PortfolioHoldingInput:
    """One holding as supplied by core-api's orchestration layer —
    `market_value` is the CURRENT market value (not cost basis), used to
    derive portfolio weights for every Phase 10 calculation that needs
    them (sector exposure, concentration risk, portfolio-weighted
    returns, optimization starting weights, etc.). `sector` is passed
    through directly from core-api's own `Instrument.sector` field
    (Phase 4) rather than this module re-deriving or looking it up
    itself — ai-service has no direct access to that table and must not
    duplicate it (same "never duplicate data" principle Phase 7 already
    established for OHLCV bars)."""

    symbol: str
    quantity: float
    market_value: float
    sector: str | None


@dataclass(frozen=True, slots=True)
class HoldingReturns:
    symbol: str
    weight: float
    sector: str | None
    daily_returns: pd.Series  # indexed by date, pct-change of adjusted_close


@dataclass(frozen=True, slots=True)
class PortfolioReturnsData:
    """The shared intermediate result every Phase 10 quantitative use
    case builds on: per-holding daily return series (for correlation/
    Sharpe/Sortino/optimization) plus each holding's portfolio weight
    (current market value / total current market value)."""

    holdings: tuple[HoldingReturns, ...]
    total_market_value: float


async def fetch_holdings_returns(
    market_data_repository: MarketDataRepository,
    holdings: list[PortfolioHoldingInput],
    lookback_days: int = 400,
    bars_out: dict[str, tuple[OhlcvBar, ...]] | None = None,
) -> PortfolioReturnsData:
    """Fetches OHLCV history for every holding via the EXISTING
    MarketDataRepository Protocol and computes each symbol's daily
    percentage-return series from adjusted_close. A holding whose
    market data cannot be fetched, or has fewer than 2 bars (not enough
    to compute even a single return), is silently excluded from the
    result — every Phase 10 use case built on this helper must therefore
    treat a partial holdings set as the normal case, not an error,
    mirroring `PortfolioCalculationService`'s own established
    "holdings_missing_price" pattern (Phase 3, core-api) for the exact
    same underlying reason: one holding's data gap must never corrupt
    every other holding's own well-formed calculation.

    `bars_out`, if supplied, is populated (keyed by uppercased symbol)
    with the RAW OhlcvBar tuples fetched for each holding — added so
    PortfolioIntelligenceUseCase can obtain the same raw bars
    AiPortfolioEngineService.compute() needs (a full OHLCV history, not
    just the derived daily-return Series this function returns) from
    this SAME fetch, rather than fetching every holding's history twice.
    Optional and defaulted to None so every existing caller (this
    function's original signature) is unaffected.
    """
    total_market_value = sum(h.market_value for h in holdings)
    end = date.today()
    start = end - timedelta(days=lookback_days)

    results: list[HoldingReturns] = []
    for holding in holdings:
        bars = await market_data_repository.get_ohlcv_bars(holding.symbol, start, end)
        if len(bars) < 2:
            continue
        closes = pd.Series(
            [bar.adjusted_close for bar in bars],
            index=pd.to_datetime([bar.bar_time for bar in bars]),
        ).sort_index()
        daily_returns = closes.pct_change().dropna()
        if daily_returns.empty:
            continue
        weight = holding.market_value / total_market_value if total_market_value > 0 else 0.0
        symbol = holding.symbol.upper()
        results.append(
            HoldingReturns(
                symbol=symbol,
                weight=weight,
                sector=holding.sector,
                daily_returns=daily_returns,
            )
        )
        if bars_out is not None:
            bars_out[symbol] = bars

    return PortfolioReturnsData(holdings=tuple(results), total_market_value=total_market_value)


def weighted_portfolio_returns(data: PortfolioReturnsData) -> pd.Series:
    """Combines each holding's own daily-return series into a single
    portfolio-level daily-return series, weighted by current market
    value — the standard "returns-based" portfolio-return approximation
    (as opposed to re-deriving it from raw portfolio value, which would
    require a full historical holdings-quantity timeline this codebase
    does not track). Uses an outer join across all holdings' date
    indices (so a newly-added holding with a shorter history doesn't
    truncate everyone else's), filling any resulting gap with 0.0 (a
    reasonable "no return contribution that day" default for a holding
    with no bar on a given date, rather than dropping the whole row).
    Shared by every Phase 10 quantitative service (analytics, risk
    metrics) that needs a single portfolio-level return series, rather
    than each one recomputing it independently."""
    if not data.holdings:
        return pd.Series(dtype=float)
    aligned = pd.concat({h.symbol: h.daily_returns for h in data.holdings}, axis=1).fillna(0.0)
    weights = pd.Series({h.symbol: h.weight for h in data.holdings})
    return aligned.mul(weights, axis=1).sum(axis=1)


def annualized_volatility_pct(returns: pd.Series) -> float:
    """Annualized Volatility (%) = daily std dev * sqrt(252) * 100 — the
    standard formula. Shared by analytics_service.py and
    risk_metrics_service.py (Standard Deviation is the same underlying
    number Task 3's own "Annualized Volatility" already computes, just
    named per Task 4's own requirement list — computed once here rather
    than duplicated in both modules)."""
    if returns.empty or len(returns) < 2:
        return 0.0
    daily_std = float(returns.std())
    return daily_std * float(np.sqrt(_TRADING_DAYS_PER_YEAR)) * 100.0
