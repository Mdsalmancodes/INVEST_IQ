"""Unit tests for the Alert entity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.domain.alerts.entities import Alert
from src.domain.alerts.exceptions import InvalidAlertConditionError, InvalidCooldownError
from src.domain.alerts.value_objects import InstrumentId


def _instrument_id() -> InstrumentId:
    return InstrumentId(uuid.uuid4())


class TestAlertCreate:
    def test_creates_with_defaults(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("150.00"),
        )
        assert alert.condition_type == "price_above"
        assert alert.threshold == Decimal("150.00")
        assert alert.is_recurring is False
        assert alert.cooldown_minutes == 0
        assert alert.is_active is True
        assert alert.triggered_at is None

    def test_can_create_as_recurring_with_cooldown(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="pct_change",
            threshold=Decimal("5.0"),
            is_recurring=True,
            cooldown_minutes=60,
        )
        assert alert.is_recurring is True
        assert alert.cooldown_minutes == 60

    @pytest.mark.parametrize(
        "condition_type", ["price_above", "price_below", "pct_change", "rsi_threshold"]
    )
    def test_accepts_all_valid_condition_types(self, condition_type: str) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type=condition_type,  # type: ignore[arg-type]
            threshold=Decimal("10"),
        )
        assert alert.condition_type == condition_type

    def test_rejects_invalid_condition_type(self) -> None:
        with pytest.raises(InvalidAlertConditionError):
            Alert.create(
                user_id="user-1",
                instrument_id=_instrument_id(),
                condition_type="volume_spike",  # type: ignore[arg-type]
                threshold=Decimal("10"),
            )

    def test_rejects_negative_cooldown(self) -> None:
        with pytest.raises(InvalidCooldownError):
            Alert.create(
                user_id="user-1",
                instrument_id=_instrument_id(),
                condition_type="price_above",
                threshold=Decimal("10"),
                cooldown_minutes=-5,
            )


class TestAlertCanTriggerNow:
    def test_can_trigger_when_active_and_never_triggered(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        assert alert.can_trigger_now() is True

    def test_cannot_trigger_when_inactive(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.deactivate()
        assert alert.can_trigger_now() is False

    def test_non_recurring_cannot_trigger_again_after_triggering(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.trigger()
        assert alert.is_active is False
        assert alert.can_trigger_now() is False

    def test_recurring_cannot_trigger_within_cooldown(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
            is_recurring=True,
            cooldown_minutes=60,
        )
        alert.trigger()
        assert alert.is_active is True
        assert alert.can_trigger_now() is False

    def test_recurring_can_trigger_again_after_cooldown_elapses(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
            is_recurring=True,
            cooldown_minutes=60,
        )
        alert.trigger()
        # Simulate cooldown having elapsed.
        alert.triggered_at = datetime.now(UTC) - timedelta(minutes=61)
        assert alert.can_trigger_now() is True

    def test_recurring_with_zero_cooldown_can_trigger_immediately_again(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
            is_recurring=True,
            cooldown_minutes=0,
        )
        alert.trigger()
        assert alert.can_trigger_now() is True


class TestAlertTrigger:
    def test_trigger_sets_triggered_at(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        assert alert.triggered_at is None
        alert.trigger()
        assert alert.triggered_at is not None

    def test_trigger_deactivates_non_recurring(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.trigger()
        assert alert.is_active is False

    def test_trigger_keeps_recurring_active(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
            is_recurring=True,
        )
        alert.trigger()
        assert alert.is_active is True


class TestAlertDeactivateReactivate:
    def test_deactivate(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.deactivate()
        assert alert.is_active is False

    def test_reactivate(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.deactivate()
        alert.reactivate()
        assert alert.is_active is True


class TestAlertUpdateCondition:
    def test_updates_threshold_only(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.update_condition(threshold=Decimal("20"))
        assert alert.threshold == Decimal("20")
        assert alert.condition_type == "price_above"

    def test_updates_condition_type(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.update_condition(condition_type="price_below")
        assert alert.condition_type == "price_below"

    def test_update_rejects_invalid_condition_type(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        with pytest.raises(InvalidAlertConditionError):
            alert.update_condition(condition_type="not_a_real_condition")  # type: ignore[arg-type]

    def test_update_rejects_negative_cooldown(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        with pytest.raises(InvalidCooldownError):
            alert.update_condition(cooldown_minutes=-1)

    def test_updates_is_recurring_and_cooldown_together(self) -> None:
        alert = Alert.create(
            user_id="user-1",
            instrument_id=_instrument_id(),
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        alert.update_condition(is_recurring=True, cooldown_minutes=30)
        assert alert.is_recurring is True
        assert alert.cooldown_minutes == 30
