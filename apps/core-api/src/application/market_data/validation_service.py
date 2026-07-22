"""MarketDataValidationService — Document 5 §11.2 stage 2 (Validate &
Dedupe): "Reject bars with null/negative prices, volume anomalies beyond N
standard deviations (circuit breaker against vendor data glitches
propagating into predictions)."

This sits between a raw provider BarResult/QuoteResult and persistence —
the ingestion pipeline (background sync, task 7) and any use case that
persists provider-sourced data both call this before writing anything,
so a single vendor glitch can never silently corrupt stored data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.application.market_data.provider import BarResult, QuoteResult

# Document 5 §11.2's "N standard deviations" threshold — a fixed multiplier
# applied to the AVERAGE of a reference volume sample (typically the
# instrument's recent trading history) rather than a true rolling
# standard deviation, since a full rolling-stddev computation requires
# historical volume data this phase's validation service doesn't have
# access to at call time (it validates one bar/quote in isolation, not a
# time series) — a disclosed simplification of "N standard deviations"
# down to "N times the reference average," which is directionally the
# same circuit-breaker intent (catch a vendor glitch reporting e.g.
# 1000x normal volume) without requiring a stateful rolling computation
# this phase doesn't build.
_VOLUME_ANOMALY_MULTIPLIER = Decimal("50")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    is_valid: bool
    rejection_reason: str | None = None


class MarketDataValidationService:
    def validate_quote(self, quote: QuoteResult) -> ValidationResult:
        if quote.price.amount <= Decimal("0"):
            return ValidationResult(
                is_valid=False, rejection_reason=f"Non-positive price: {quote.price}"
            )
        if quote.previous_close is not None and quote.previous_close.amount < Decimal("0"):
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"Negative previous_close: {quote.previous_close}",
            )
        return ValidationResult(is_valid=True)

    def validate_bar(
        self, bar: BarResult, reference_average_volume: int | None = None
    ) -> ValidationResult:
        if bar.open.amount <= Decimal("0") or bar.close.amount <= Decimal("0"):
            return ValidationResult(
                is_valid=False, rejection_reason="Non-positive open/close price"
            )
        if bar.high.amount < bar.low.amount:
            return ValidationResult(
                is_valid=False, rejection_reason=f"high ({bar.high}) < low ({bar.low})"
            )
        if not (bar.low.amount <= bar.open.amount <= bar.high.amount):
            return ValidationResult(
                is_valid=False, rejection_reason="open outside [low, high] range"
            )
        if not (bar.low.amount <= bar.close.amount <= bar.high.amount):
            return ValidationResult(
                is_valid=False, rejection_reason="close outside [low, high] range"
            )
        if bar.volume < 0:
            return ValidationResult(is_valid=False, rejection_reason="Negative volume")

        if reference_average_volume is not None and reference_average_volume > 0:
            threshold = Decimal(reference_average_volume) * _VOLUME_ANOMALY_MULTIPLIER
            if Decimal(bar.volume) > threshold:
                return ValidationResult(
                    is_valid=False,
                    rejection_reason=(
                        f"Volume anomaly: {bar.volume} exceeds "
                        f"{_VOLUME_ANOMALY_MULTIPLIER}x reference average "
                        f"({reference_average_volume})"
                    ),
                )
        return ValidationResult(is_valid=True)

    def dedupe_bars(self, bars: tuple[BarResult, ...]) -> tuple[BarResult, ...]:
        """Per Document 5 §11.2 stage 2: "Dedupe by (symbol, timestamp,
        vendor) — a reconnected stream replaying the last few ticks must
        not double-count." Keeps the LAST occurrence of each key (a
        re-fetch of an in-progress bar should reflect its most recent,
        presumably more complete, state)."""
        seen: dict[tuple[str, object, str], BarResult] = {}
        for bar in bars:
            key = (bar.symbol, bar.bar_time, bar.source)
            seen[key] = bar
        return tuple(seen.values())
