"""EvaluateAlertsUseCase — the Alert Evaluation Engine, closing the
standing Phase 6/7/8 known-issue: Alert.can_trigger_now()/trigger()
(domain methods, fully unit-tested since Phase 6) have existed since
Phase 6 but nothing has ever called them. This use case is that missing
caller.

Named to match the exact "AlertEvaluationService" terminology already
anticipated in alert_models.py's own Phase 6 module docstring (that
comment names the notification_preferences columns as "not yet consulted
by AlertEvaluationService" — this use case is the concrete
implementation of what that comment was describing).

Given a symbol and its current price (plus enough recent OHLCV history
for RSI, when relevant), evaluates every active alert on that instrument
(AlertRepository.list_active_for_instrument — Phase 6, unmodified,
explicitly documented as "used by the alert evaluation engine") against
its condition_type/threshold, using Alert's own can_trigger_now()/
trigger() domain methods for the actual trigger-and-cooldown logic (this
use case does not re-implement any of Alert's own invariants — it only
decides WHETHER a condition is currently met, then defers entirely to
the entity for whether it's allowed to fire again right now).

On a trigger: persists the Alert (trigger() mutates triggered_at/
is_active in place — Phase 6 entities), creates and persists a
Notification (Notification.create() — Phase 6, unmodified) recording the
event, and returns it so the caller (AlertEvaluationStreamingService)
can publish it over WebSocket — this use case has no WebSocket/Redis
dependency itself, keeping it a plain, directly-testable application-
layer use case, matching every other use case in this codebase's
convention of "the use case does persistence; the presentation/
infrastructure layer does transport."

CONDITION TYPE SEMANTICS (not documented anywhere else — Alert's own
domain module only names the 4 condition_type literals, so this use
case is the first place their actual trigger semantics are defined):
- price_above: triggers when current_price >= threshold
- price_below: triggers when current_price <= threshold
- pct_change: triggers when abs(daily_change_pct) >= threshold (a
  magnitude threshold — the founder's "stop loss hit" and "target price
  hit" language covers both price_above/price_below directly, so
  pct_change covers the "moved by more than X%" case as a magnitude, not
  a directional threshold)
- rsi_threshold: triggers when the 14-period RSI (computed here directly
  from OhlcvBarRepository — a self-contained implementation, not
  borrowed from ai-service's own separate RSI indicator, since these are
  two different services with no shared dependency between them) meets
  or exceeds `threshold` (a classic overbought/oversold signal — this
  use case does not distinguish "above" vs "below" for RSI the way
  price_above/price_below do; the founder's alert list names
  "target price/stop loss/portfolio threshold/prediction/sentiment" as
  the trigger conditions, RSI itself wasn't singled out with a
  direction, so a single ">=" semantic was chosen as the simplest
  faithful interpretation of the existing rsi_threshold condition type)

DISCLOSED SCOPE BOUNDARY: "portfolio threshold crossed," "prediction
changes," and "sentiment changes" (also named in the founder's Live
Alerts requirement) are NOT evaluated by this use case — Alert's own
VALID_CONDITION_TYPES (Phase 6, frozen) has no condition type
representing any of these three. Adding new condition-type literals to
Alert's frozenset/Literal would be the smallest possible additive change
that could support them, but doing so without any corresponding
threshold-comparison semantics defined anywhere (what does "portfolio
threshold" even compare against — the whole portfolio's value against a
per-alert Decimal? which portfolio, since Alert has no portfolio_id
field at all today?) would mean inventing a materially new alert
sub-type, not implementing an existing one — judged out of scope for
this task and disclosed in docs/phase-9/known-issues.md rather than
either silently skipped or hastily half-implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import AlertRepository
from src.domain.alerts.value_objects import InstrumentId
from src.domain.notifications.entities import Notification
from src.domain.notifications.repositories import NotificationRepository

_RSI_PERIOD = 14


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    """The current market data this use case evaluates alerts against —
    deliberately a small, self-contained dataclass (not
    CurrentPriceResult/QuoteTick, both of which carry fields this use
    case has no need for) so the use case's own signature stays exactly
    as wide as what it actually consumes."""

    price: Decimal
    daily_change_pct: Decimal | None
    closing_prices_ascending: tuple[Decimal, ...]
    """Most recent closes, oldest first (matching OhlcvBarRepository.query's
    own documented ordering) — used for RSI. May be empty/short; RSI
    condition types simply never trigger if there isn't enough history
    (_RSI_PERIOD + 1 closes), rather than raising."""


@dataclass(frozen=True, slots=True)
class EvaluateAlertsCommand:
    instrument_id: InstrumentId
    snapshot: PriceSnapshot


class EvaluateAlertsUseCase:
    def __init__(
        self, alert_repository: AlertRepository, notification_repository: NotificationRepository
    ) -> None:
        self._alert_repository = alert_repository
        self._notification_repository = notification_repository

    async def execute(self, command: EvaluateAlertsCommand) -> tuple[Notification, ...]:
        alerts = await self._alert_repository.list_active_for_instrument(command.instrument_id)

        triggered_notifications: list[Notification] = []
        for alert in alerts:
            if not alert.can_trigger_now():
                continue
            if not _condition_is_met(alert, command.snapshot):
                continue

            alert.trigger()
            await self._alert_repository.save(alert)

            notification = Notification.create(
                user_id=alert.user_id,
                type="alert_triggered",
                title=_notification_title(alert),
                body=_notification_body(alert, command.snapshot),
                metadata={
                    "alert_id": str(alert.id),
                    "instrument_id": str(alert.instrument_id),
                    "condition_type": alert.condition_type,
                    "threshold": str(alert.threshold),
                    "price": str(command.snapshot.price),
                },
            )
            await self._notification_repository.save(notification)
            triggered_notifications.append(notification)

        return tuple(triggered_notifications)


def _condition_is_met(alert: Alert, snapshot: PriceSnapshot) -> bool:
    if alert.condition_type == "price_above":
        return snapshot.price >= alert.threshold
    if alert.condition_type == "price_below":
        return snapshot.price <= alert.threshold
    if alert.condition_type == "pct_change":
        if snapshot.daily_change_pct is None:
            return False
        return abs(snapshot.daily_change_pct) >= alert.threshold
    if alert.condition_type == "rsi_threshold":
        rsi = _compute_rsi(snapshot.closing_prices_ascending)
        if rsi is None:
            return False
        return rsi >= alert.threshold
    return False  # pragma: no cover - Alert.create/update_condition already
    # reject any condition_type outside VALID_CONDITION_TYPES, so this
    # branch is unreachable for a well-formed Alert; kept only as an
    # explicit, safe default rather than an unhandled fallthrough.


def _compute_rsi(closes_ascending: tuple[Decimal, ...]) -> Decimal | None:
    """Standard 14-period RSI (Wilder's smoothing simplified to a plain
    average over the window, the same simplification level as most
    introductory RSI implementations — this use case does not need
    Wilder's exact exponential smoothing to serve as a meaningful
    overbought/oversold trigger signal). Returns None when there isn't
    enough history (_RSI_PERIOD + 1 closes) to compute a value at all,
    rather than raising — the caller treats this as "condition not met,"
    not an error, since a newly-listed or thinly-tracked instrument
    simply may not have enough bars yet."""
    if len(closes_ascending) < _RSI_PERIOD + 1:
        return None

    window = closes_ascending[-(_RSI_PERIOD + 1) :]
    gains = Decimal("0")
    losses = Decimal("0")
    for previous, current in zip(window[:-1], window[1:], strict=True):
        delta = current - previous
        if delta > 0:
            gains += delta
        else:
            losses += -delta

    avg_gain = gains / _RSI_PERIOD
    avg_loss = losses / _RSI_PERIOD
    if avg_loss == 0:
        return Decimal("100")
    relative_strength = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))


def _notification_title(alert: Alert) -> str:
    return f"Alert triggered: {alert.condition_type.replace('_', ' ')}"


def _notification_body(alert: Alert, snapshot: PriceSnapshot) -> str:
    return (
        f"Your {alert.condition_type.replace('_', ' ')} alert "
        f"(threshold {alert.threshold}) was triggered at price {snapshot.price}."
    )
