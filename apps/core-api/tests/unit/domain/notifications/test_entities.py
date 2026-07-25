"""Unit tests for the Notification and NotificationPreferences entities."""

from __future__ import annotations

from datetime import time

import pytest

from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.exceptions import InvalidDigestFrequencyError


class TestNotificationCreate:
    def test_creates_with_defaults(self) -> None:
        notification = Notification.create(
            user_id="user-1",
            type="alert_triggered",
            title="AAPL crossed $150",
            body="Your price alert for AAPL has triggered.",
        )
        assert notification.user_id == "user-1"
        assert notification.type == "alert_triggered"
        assert notification.metadata == {}
        assert notification.read_at is None
        assert notification.is_read is False

    def test_creates_with_metadata(self) -> None:
        notification = Notification.create(
            user_id="user-1",
            type="alert_triggered",
            title="AAPL crossed $150",
            body="Your price alert for AAPL has triggered.",
            metadata={"symbol": "AAPL", "price": "151.20"},
        )
        assert notification.metadata == {"symbol": "AAPL", "price": "151.20"}


class TestNotificationMarkAsRead:
    def test_marks_as_read(self) -> None:
        notification = Notification.create(
            user_id="user-1", type="system", title="Welcome", body="Welcome to INVEST IQ."
        )
        notification.mark_as_read()
        assert notification.is_read is True
        assert notification.read_at is not None

    def test_marking_as_read_twice_is_idempotent(self) -> None:
        notification = Notification.create(
            user_id="user-1", type="system", title="Welcome", body="Welcome to INVEST IQ."
        )
        notification.mark_as_read()
        first_read_at = notification.read_at

        notification.mark_as_read()

        assert notification.read_at == first_read_at


class TestNotificationPreferencesCreateDefault:
    def test_creates_with_expected_defaults(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        assert prefs.user_id == "user-1"
        assert prefs.price_alerts_email is True
        assert prefs.price_alerts_push is True
        assert prefs.digest_frequency == "daily"
        assert prefs.quiet_hours_start is None
        assert prefs.quiet_hours_end is None


class TestNotificationPreferencesUpdate:
    def test_updates_email_and_push_toggles(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        prefs.update(price_alerts_email=False, price_alerts_push=False)
        assert prefs.price_alerts_email is False
        assert prefs.price_alerts_push is False

    def test_updates_digest_frequency(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        prefs.update(digest_frequency="weekly")
        assert prefs.digest_frequency == "weekly"

    def test_rejects_invalid_digest_frequency(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        with pytest.raises(InvalidDigestFrequencyError):
            prefs.update(digest_frequency="hourly")  # type: ignore[arg-type]

    def test_sets_quiet_hours(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        prefs.update(quiet_hours_start=time(22, 0), quiet_hours_end=time(7, 0))
        assert prefs.quiet_hours_start == time(22, 0)
        assert prefs.quiet_hours_end == time(7, 0)

    def test_clears_quiet_hours(self) -> None:
        prefs = NotificationPreferences.create_default("user-1")
        prefs.update(quiet_hours_start=time(22, 0), quiet_hours_end=time(7, 0))

        prefs.update(clear_quiet_hours=True)

        assert prefs.quiet_hours_start is None
        assert prefs.quiet_hours_end is None
