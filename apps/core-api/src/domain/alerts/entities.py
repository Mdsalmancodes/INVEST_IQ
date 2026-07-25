"""Domain entity for the alerts bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(alerts — exact frozen DDL) and alert_models.py's module docstring for the
disclosed scope decision (triggered alerts persist to `notifications`,
not a Redis Stream, since the real-time layer is a later phase).

The Alert entity owns its own trigger/rearm lifecycle: `trigger()` records
`triggered_at` and, for non-recurring alerts, deactivates itself
(`is_active = False`) so a one-shot alert never fires twice — mirroring
Watchlist's "aggregate owns its invariants" rule (Document 3 §3.4). A
recurring alert instead stays active and relies on `cooldown_minutes` (via
`can_trigger_now()`) to avoid re-firing on every single evaluation tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from src.domain.alerts.exceptions import InvalidAlertConditionError, InvalidCooldownError
from src.domain.alerts.value_objects import AlertId, InstrumentId

ConditionType = Literal["price_above", "price_below", "pct_change", "rsi_threshold"]

VALID_CONDITION_TYPES: frozenset[str] = frozenset(
    {"price_above", "price_below", "pct_change", "rsi_threshold"}
)


@dataclass(slots=True)
class Alert:
    """A user-defined trigger condition on an instrument. Not an aggregate
    root with owned children (unlike Watchlist) — Alert has no child
    entities, so it is itself the whole aggregate, matching Portfolio's
    Holding-less-transaction style for simple entities.
    """

    id: AlertId
    user_id: str
    instrument_id: InstrumentId
    condition_type: ConditionType
    threshold: Decimal
    is_recurring: bool
    cooldown_minutes: int
    is_active: bool
    triggered_at: datetime | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        user_id: str,
        instrument_id: InstrumentId,
        condition_type: ConditionType,
        threshold: Decimal,
        is_recurring: bool = False,
        cooldown_minutes: int = 0,
    ) -> Alert:
        _validate_condition_type(condition_type)
        _validate_cooldown(cooldown_minutes)
        return cls(
            id=AlertId.new(),
            user_id=user_id,
            instrument_id=instrument_id,
            condition_type=condition_type,
            threshold=threshold,
            is_recurring=is_recurring,
            cooldown_minutes=cooldown_minutes,
            is_active=True,
            triggered_at=None,
            created_at=datetime.now(UTC),
        )

    def can_trigger_now(self) -> bool:
        """False if the alert is inactive, or if it's recurring and still
        within its cooldown window since the last trigger — the
        evaluation engine's single gate before creating a Notification,
        so cooldown enforcement lives once here rather than being
        re-implemented at each call site."""
        if not self.is_active:
            return False
        if self.triggered_at is None:
            return True
        if not self.is_recurring:
            return False
        cooldown_elapsed = datetime.now(UTC) - self.triggered_at
        return cooldown_elapsed >= timedelta(minutes=self.cooldown_minutes)

    def trigger(self) -> None:
        """Records the trigger timestamp. Non-recurring alerts deactivate
        immediately (one-shot semantics); recurring alerts stay active and
        rely on can_trigger_now()'s cooldown check for the next tick."""
        self.triggered_at = datetime.now(UTC)
        if not self.is_recurring:
            self.is_active = False

    def deactivate(self) -> None:
        self.is_active = False

    def reactivate(self) -> None:
        self.is_active = True

    def update_condition(
        self,
        condition_type: ConditionType | None = None,
        threshold: Decimal | None = None,
        is_recurring: bool | None = None,
        cooldown_minutes: int | None = None,
    ) -> None:
        if condition_type is not None:
            _validate_condition_type(condition_type)
            self.condition_type = condition_type
        if threshold is not None:
            self.threshold = threshold
        if is_recurring is not None:
            self.is_recurring = is_recurring
        if cooldown_minutes is not None:
            _validate_cooldown(cooldown_minutes)
            self.cooldown_minutes = cooldown_minutes


def _validate_condition_type(condition_type: str) -> None:
    if condition_type not in VALID_CONDITION_TYPES:
        raise InvalidAlertConditionError(
            f"Invalid condition_type {condition_type!r}; must be one of "
            f"{sorted(VALID_CONDITION_TYPES)}"
        )


def _validate_cooldown(cooldown_minutes: int) -> None:
    if cooldown_minutes < 0:
        raise InvalidCooldownError(
            f"cooldown_minutes cannot be negative, got {cooldown_minutes}"
        )
