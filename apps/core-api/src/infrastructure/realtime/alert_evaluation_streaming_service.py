"""AlertEvaluationStreamingService — Phase 9's "Live Alerts" requirement:
push a notification the instant a target price/stop loss/RSI/%-change
condition is met. This is what finally closes the standing Phase 6/7/8
known-issue that Alert.can_trigger_now()/trigger() existed but nothing
ever called them (see evaluate_alerts_use_case.py's own module
docstring for the full Alert Evaluation Engine writeup).

WHY INDEPENDENT REDIS SUBSCRIPTION, NOT A HOOK INTO
MarketDataStreamingService (task 3): this service subscribes to
"realtime:quote:*" via RedisBroker.psubscribe_and_dispatch — the SAME
mechanism RealtimeService (task 2) already uses to fan out to
WebSocket clients — rather than MarketDataStreamingService calling into
this service directly after each tick. Two reasons: (1) task 3's
MarketDataStreamingService is already built, tested, and verified;
adding an alert-evaluation extension point to its signature would mean
touching completed Phase 9 code for a capability it doesn't need to
know about. (2) subscribing to the published Redis message (rather than
being called in-process) is horizontally-scalability-correct for free —
this service correctly evaluates alerts against a quote tick published
by ANY core-api instance, not just whichever instance happens to run
this particular AlertEvaluationStreamingService, matching the same
"any instance's publish reaches every instance's own subscribers"
principle RealtimeService itself already establishes.

Each received quote message triggers exactly one call to
EvaluateAlertsUseCase for that symbol's instrument — RSI needs recent
OHLCV history, so this service also queries a short window of closes
via the EXISTING OhlcvBarRepository (unmodified) each time, using the
same session-per-call pattern as every other Phase 9 streaming service.
On a trigger, in addition to what EvaluateAlertsUseCase already
persists (the Alert row + Notification row), this service publishes the
Notification over WebSocket to channels.alert_channel(user_id) — the
actual "push notification instantly" delivery mechanism.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from decimal import Decimal

from observability import get_logger

from src.application.alerts.evaluate_alerts_use_case import (
    EvaluateAlertsCommand,
    EvaluateAlertsUseCase,
    PriceSnapshot,
)
from src.domain.alerts.repositories import AlertRepository
from src.domain.market_data.repositories import (
    InstrumentRepository,
    OhlcvBarQuery,
    OhlcvBarRepository,
)
from src.domain.market_data.value_objects import Interval
from src.domain.notifications.entities import Notification
from src.domain.notifications.repositories import NotificationRepository
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.redis_broker import RedisBroker

logger = get_logger(__name__)

_RSI_HISTORY_LOOKBACK_BARS = 30
"""More than the 15 bars EvaluateAlertsUseCase's RSI computation strictly
needs (_RSI_PERIOD + 1 = 15) — a small buffer so a symbol with slightly
gappy history still has enough closes, without querying an unbounded
window every single quote tick."""


@dataclass(frozen=True, slots=True)
class AlertEvaluationDependencies:
    alert_repository: AlertRepository
    notification_repository: NotificationRepository
    instrument_repository: InstrumentRepository
    ohlcv_bar_repository: OhlcvBarRepository


DependencyFactory = Callable[[object], AlertEvaluationDependencies]


class AlertEvaluationStreamingService:
    def __init__(
        self,
        redis_broker: RedisBroker,
        session_scope: Callable[[], AbstractAsyncContextManager[object]],
        dependency_factory: DependencyFactory,
    ) -> None:
        self._redis_broker = redis_broker
        self._session_scope = session_scope
        self._dependency_factory = dependency_factory
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._redis_broker.psubscribe_and_dispatch(
                ["realtime:quote:*"], self._handle_quote_message, stop_event=self._stop_event
            )
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def handle_quote(
        self, symbol: str, payload: dict[str, object]
    ) -> tuple[Notification, ...]:
        """Evaluates alerts for one already-decoded quote payload —
        public so tests can invoke it directly, deterministically,
        without a real Redis round-trip. Returns every Notification
        created this call (empty if nothing triggered), matching
        EvaluateAlertsUseCase's own return contract."""
        price_raw = payload.get("price")
        if price_raw is None:
            return ()
        price = Decimal(str(price_raw))
        change_pct_raw = payload.get("change_pct")
        change_pct = Decimal(str(change_pct_raw)) if change_pct_raw is not None else None

        async with self._session_scope() as session:
            deps = self._dependency_factory(session)
            instrument = await deps.instrument_repository.get_by_symbol(symbol)
            if instrument is None:
                return ()

            closes = await self._recent_closes(deps.ohlcv_bar_repository, instrument.id)
            snapshot = PriceSnapshot(
                price=price, daily_change_pct=change_pct, closing_prices_ascending=closes
            )
            use_case = EvaluateAlertsUseCase(deps.alert_repository, deps.notification_repository)
            notifications = await use_case.execute(
                EvaluateAlertsCommand(instrument_id=instrument.id, snapshot=snapshot)
            )

        for notification in notifications:
            await self._redis_broker.publish(
                channels.alert_channel(notification.user_id), _notification_to_payload(notification)
            )
        return notifications

    async def _recent_closes(
        self, ohlcv_bar_repository: OhlcvBarRepository, instrument_id: object
    ) -> tuple[Decimal, ...]:
        bars = await ohlcv_bar_repository.query(
            OhlcvBarQuery(instrument_id=instrument_id, interval=Interval.ONE_DAY)  # type: ignore[arg-type]
        )
        recent = bars[-_RSI_HISTORY_LOOKBACK_BARS:]
        return tuple(bar.close.amount for bar in recent)

    async def _handle_quote_message(self, channel: str, payload: dict[str, object]) -> None:
        symbol = channel.removeprefix("realtime:quote:")
        try:
            await self.handle_quote(symbol, payload)
        except Exception as exc:  # noqa: BLE001 - one symbol's evaluation
            # failure must never take down the whole subscription loop;
            # the next published quote for any symbol still gets handled.
            logger.warning("realtime.alert_evaluation.failed", symbol=symbol, error=str(exc))


def _notification_to_payload(notification: Notification) -> dict[str, object]:
    return {
        "id": str(notification.id),
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "metadata": notification.metadata,
        "created_at": notification.created_at.isoformat(),
    }
