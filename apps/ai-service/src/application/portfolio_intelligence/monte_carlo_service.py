"""MonteCarloService — Phase 10 Monte Carlo Simulation.

Supports 100/500/1000/5000 simulation runs (per the founder's explicit
list), producing a future-portfolio-value distribution, confidence
intervals, and explicit worst/expected/best case figures.

METHOD — HISTORICAL RETURNS BOOTSTRAP, NOT PARAMETRIC SAMPLING:
each simulated day's return is drawn (with replacement) from the
portfolio's OWN observed historical daily returns (from
PortfolioReturnsData), rather than sampled from a fitted normal/log-
normal distribution. This is consistent with Task 4's own already-
established preference for historical/non-parametric methods over
parametric ones (VaR/CVaR/Expected Shortfall all chose historical for
the same reason) — real equity returns are fat-tailed, and bootstrapping
directly from observed history makes no distributional assumption that
could understate tail risk. Disclosed here as the specific method
chosen, since Monte Carlo simulation can legitimately be implemented
several different ways and no existing spec in this codebase mandates
one.

TIME HORIZON: defaults to 252 trading days (1 year) — a disclosed
default, not a fixed requirement, exposed as a parameter so a caller can
simulate a different horizon.

FAN-CHART CHECKPOINTS: the founder's requirement list names both "Future
Portfolio Value" (implying a value-over-time fan chart) and "Probability
Distribution" (implying a single end-of-horizon histogram) — this
service produces both from the SAME simulation run rather than running
twice. Tracking percentiles at EVERY simulated day for 5000 runs would
produce an unnecessarily large payload; percentiles are instead computed
at a monthly cadence (every 21 trading days, matching
analytics_service's own _TRADING_DAYS_PER_MONTH convention) plus the
final day, which is enough points for a smooth-looking fan chart without
an unbounded response size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.application.portfolio_intelligence.data import (
    PortfolioReturnsData,
    weighted_portfolio_returns,
)

_DEFAULT_TRADING_DAYS_HORIZON = 252
_CHECKPOINT_INTERVAL_DAYS = 21
_VALID_RUN_COUNTS = frozenset({100, 500, 1000, 5000})


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    day: int
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    num_runs: int
    horizon_days: int
    starting_value: float
    confidence_intervals: tuple[ConfidenceInterval, ...]
    """Percentile bands at each checkpoint day — the "Future Portfolio
    Value" fan-chart data, and the source of the "Confidence Intervals"
    requirement (each ConfidenceInterval IS a confidence band at that
    day)."""
    final_value_distribution: tuple[float, ...]
    """Every individual simulated run's final portfolio value — the raw
    "Probability Distribution" data a frontend histogram renders
    directly."""
    worst_case_value: float
    """5th percentile of the final-value distribution."""
    expected_case_value: float
    """50th percentile (median, not mean — more robust to the
    fat-tailed/skewed distributions a bootstrap can produce) of the
    final-value distribution."""
    best_case_value: float
    """95th percentile of the final-value distribution."""


class InvalidSimulationRunCountError(ValueError):
    """Raised when a caller requests a run count outside the founder's
    explicit supported list (100/500/1000/5000) — this is deliberately a
    closed set, not an arbitrary integer, since the founder's own
    requirement enumerates exactly these 4 values."""


class MonteCarloService:
    def simulate(
        self,
        data: PortfolioReturnsData,
        num_runs: int,
        horizon_days: int = _DEFAULT_TRADING_DAYS_HORIZON,
        seed: int | None = None,
    ) -> MonteCarloResult:
        if num_runs not in _VALID_RUN_COUNTS:
            raise InvalidSimulationRunCountError(
                f"num_runs must be one of {sorted(_VALID_RUN_COUNTS)}, got {num_runs}"
            )

        starting_value = data.total_market_value
        portfolio_returns = weighted_portfolio_returns(data)

        if portfolio_returns.empty or starting_value <= 0:
            # Nothing to bootstrap from (no holdings, or a zero-value
            # portfolio) — every run trivially stays at the starting
            # value rather than raising, matching this module's
            # established "a degenerate input produces a well-formed
            # zeroed/flat result, not an exception" convention.
            flat_intervals = tuple(
                ConfidenceInterval(
                    day=day, p5=starting_value, p25=starting_value, p50=starting_value,
                    p75=starting_value, p95=starting_value,
                )
                for day in _checkpoint_days(horizon_days)
            )
            return MonteCarloResult(
                num_runs=num_runs,
                horizon_days=horizon_days,
                starting_value=starting_value,
                confidence_intervals=flat_intervals,
                final_value_distribution=tuple([starting_value] * num_runs),
                worst_case_value=starting_value,
                expected_case_value=starting_value,
                best_case_value=starting_value,
            )

        rng = np.random.default_rng(seed)
        historical_returns = portfolio_returns.to_numpy()

        # Bootstrap-sample (num_runs x horizon_days) daily returns with
        # replacement in one vectorized call, then compound each run's
        # own daily-return path into a running value-multiplier path —
        # far faster than a Python-level double loop for 5000 runs *
        # 252 days.
        sampled_returns = rng.choice(historical_returns, size=(num_runs, horizon_days))
        cumulative_multipliers = np.cumprod(1.0 + sampled_returns, axis=1)
        value_paths = starting_value * cumulative_multipliers

        checkpoint_days = _checkpoint_days(horizon_days)
        confidence_intervals = tuple(
            _confidence_interval_at(value_paths, day, starting_value) for day in checkpoint_days
        )

        final_values = value_paths[:, -1]
        worst_case = float(np.percentile(final_values, 5))
        expected_case = float(np.percentile(final_values, 50))
        best_case = float(np.percentile(final_values, 95))

        return MonteCarloResult(
            num_runs=num_runs,
            horizon_days=horizon_days,
            starting_value=starting_value,
            confidence_intervals=confidence_intervals,
            final_value_distribution=tuple(float(v) for v in final_values),
            worst_case_value=worst_case,
            expected_case_value=expected_case,
            best_case_value=best_case,
        )


def _checkpoint_days(horizon_days: int) -> tuple[int, ...]:
    """Day 0 (the starting point) plus every _CHECKPOINT_INTERVAL_DAYS-th
    day, always including the final horizon day even if it doesn't land
    exactly on a checkpoint interval."""
    days = list(range(0, horizon_days + 1, _CHECKPOINT_INTERVAL_DAYS))
    if days[-1] != horizon_days:
        days.append(horizon_days)
    return tuple(days)


def _confidence_interval_at(
    value_paths: np.ndarray[tuple[int, int], np.dtype[np.float64]], day: int, starting_value: float
) -> ConfidenceInterval:
    if day == 0:
        # Day 0 is before any simulated return has been applied — every
        # run starts at the exact same known starting value, so its
        # "distribution" is degenerate (all 5 percentiles equal to the
        # single known starting value, not derived from value_paths at
        # all — value_paths' own column 0 already reflects day 1's
        # return, not day 0's absence of one).
        return ConfidenceInterval(
            day=0, p5=starting_value, p25=starting_value, p50=starting_value,
            p75=starting_value, p95=starting_value,
        )
    column = value_paths[:, day - 1]
    return ConfidenceInterval(
        day=day,
        p5=float(np.percentile(column, 5)),
        p25=float(np.percentile(column, 25)),
        p50=float(np.percentile(column, 50)),
        p75=float(np.percentile(column, 75)),
        p95=float(np.percentile(column, 95)),
    )
