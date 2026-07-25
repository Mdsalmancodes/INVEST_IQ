"""Tests for EvaluateAlertsUseCase — the Alert Evaluation Engine. Real
Alert/Notification entities (Phase 6, unmodified) exercising their own
real can_trigger_now()/trigger() domain methods; fakes only for the
repository boundary, matching the established Phase 6 test convention
(test_use_cases.py's own FakeAlertRepository)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from src.application.alerts.evaluate_alerts_use_case import (
    EvaluateAlertsCommand,
    EvaluateAlertsUseCase,
    PriceSnapshot,
)
from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import AlertListFilter, AlertPageResult
from src.domain.alerts.value_objects import AlertId, InstrumentId
from src.domain.notifications.entities import Notification
from src.domain.notifications.value_objects import NotificationId

AAPL_ID = InstrumentId(uuid.uuid4())


class FakeAlertRepository:
    def __init__(self, alerts: list[Alert] | None = None) -> None:
        self._store: dict[str, Alert] = {str(a.id): a for a in (alerts or [])}
        self.saved: list[Alert] = []

    async def save(self, alert: Alert) -> None:
        self._store[str(alert.id)] = alert
        self.saved.append(alert)

    async def get_by_id(self, alert_id: AlertId) -> Alert | None:
        return self._store.get(str(alert_id))

    async def list_for_user(self, user_id: str, filters: AlertListFilter) -> AlertPageResult:
        raise NotImplementedError

    async def list_active_for_instrument(self, instrument_id: InstrumentId) -> tuple[Alert, ...]:
        return tuple(
            a for a in self._store.values() if a.instrument_id == instrument_id and a.is_active
        )

    async def delete(self, alert_id: AlertId) -> None:
        self._store.pop(str(alert_id), None)

    async def exists_duplicate(
        self,
        user_id: str,
        instrument_id: InstrumentId,
        condition_type: str,
        threshold: object,
        exclude_alert_id: AlertId | None = None,
    ) -> bool:
        return False


class FakeNotificationRepository:
    def __init__(self) -> None:
        self.saved: list[Notification] = []

    async def save(self, notification: Notification) -> None:
        self.saved.append(notification)

    async def get_by_id(self, notification_id: NotificationId) -> Notification | None:
        return None

    async def list_for_user(self, user_id: str, filters: object) -> object:
        raise NotImplementedError

    async def mark_all_as_read_for_user(self, user_id: str) -> int:
        raise NotImplementedError


def _make_alert(
    condition_type: str, threshold: str, *, instrument_id: InstrumentId = AAPL_ID
) -> Alert:
    return Alert.create(
        user_id=str(uuid.uuid4()),
        instrument_id=instrument_id,
        condition_type=condition_type,  # type: ignore[arg-type]
        threshold=Decimal(threshold),
    )


def _snapshot(
    price: str, change_pct: str | None = None, closes: tuple[str, ...] = ()
) -> PriceSnapshot:
    return PriceSnapshot(
        price=Decimal(price),
        daily_change_pct=Decimal(change_pct) if change_pct is not None else None,
        closing_prices_ascending=tuple(Decimal(c) for c in closes),
    )


class TestPriceAboveBelow:
    async def test_price_above_triggers_when_price_meets_threshold(self) -> None:
        alert = _make_alert("price_above", "150")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("150"))
        )

        assert len(result) == 1
        assert alert.triggered_at is not None
        assert alert.is_active is False  # non-recurring, one-shot deactivation
        assert len(notification_repo.saved) == 1

    async def test_price_above_does_not_trigger_below_threshold(self) -> None:
        alert = _make_alert("price_above", "150")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("149.99"))
        )

        assert result == ()
        assert alert.triggered_at is None

    async def test_price_below_triggers_when_price_meets_threshold(self) -> None:
        alert = _make_alert("price_below", "100")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("99.5"))
        )

        assert len(result) == 1


class TestPctChange:
    async def test_triggers_on_magnitude_regardless_of_direction(self) -> None:
        alert = _make_alert("pct_change", "5")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(
                instrument_id=AAPL_ID, snapshot=_snapshot("100", change_pct="-6.2")
            )
        )

        assert len(result) == 1

    async def test_does_not_trigger_when_no_change_pct_is_available(self) -> None:
        alert = _make_alert("pct_change", "5")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("100"))
        )

        assert result == ()


class TestRsiThreshold:
    async def test_triggers_when_rsi_meets_threshold(self) -> None:
        # 15 strictly-increasing closes -> all gains, no losses -> RSI = 100.
        closes = tuple(str(100 + i) for i in range(15))
        alert = _make_alert("rsi_threshold", "70")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(
                instrument_id=AAPL_ID, snapshot=_snapshot("114", closes=closes)
            )
        )

        assert len(result) == 1

    async def test_does_not_trigger_with_insufficient_history(self) -> None:
        alert = _make_alert("rsi_threshold", "70")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(
                instrument_id=AAPL_ID, snapshot=_snapshot("100", closes=("100", "101"))
            )
        )

        assert result == ()


class TestTriggerAndCooldownSemantics:
    async def test_a_non_recurring_alert_never_triggers_twice(self) -> None:
        alert = _make_alert("price_above", "100")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        first = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("101"))
        )
        second = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("102"))
        )

        assert len(first) == 1
        assert second == ()  # is_active became False after the first trigger

    async def test_a_recurring_alert_respects_its_cooldown(self) -> None:
        alert = Alert.create(
            user_id=str(uuid.uuid4()),
            instrument_id=AAPL_ID,
            condition_type="price_above",
            threshold=Decimal("100"),
            is_recurring=True,
            cooldown_minutes=60,
        )
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        first = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("101"))
        )
        second = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("102"))
        )

        assert len(first) == 1
        assert second == ()  # still within the 60-minute cooldown
        assert alert.is_active is True  # recurring alerts stay active

    async def test_an_inactive_alert_is_never_evaluated(self) -> None:
        alert = _make_alert("price_above", "100")
        alert.deactivate()
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("101"))
        )

        assert result == ()


class TestMultipleAlertsAndNotificationContent:
    async def test_multiple_alerts_on_the_same_instrument_are_evaluated_independently(
        self,
    ) -> None:
        triggering_alert = _make_alert("price_above", "100")
        non_triggering_alert = _make_alert("price_above", "500")
        alert_repo = FakeAlertRepository([triggering_alert, non_triggering_alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("101"))
        )

        assert len(result) == 1
        assert non_triggering_alert.triggered_at is None

    async def test_the_created_notification_carries_the_triggering_alerts_metadata(self) -> None:
        alert = _make_alert("price_above", "100")
        alert_repo = FakeAlertRepository([alert])
        notification_repo = FakeNotificationRepository()
        use_case = EvaluateAlertsUseCase(alert_repo, notification_repo)  # type: ignore[arg-type]

        result = await use_case.execute(
            EvaluateAlertsCommand(instrument_id=AAPL_ID, snapshot=_snapshot("101"))
        )

        notification = result[0]
        assert notification.type == "alert_triggered"
        assert notification.user_id == alert.user_id
        assert notification.metadata["alert_id"] == str(alert.id)
        assert notification.metadata["condition_type"] == "price_above"
