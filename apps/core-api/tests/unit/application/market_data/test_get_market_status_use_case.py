"""Unit tests for GetMarketStatusUseCase — since this depends on
datetime.now(), tests inject known instants by monkeypatching the
use case module's `datetime` reference to a frozen subclass, verified
against fixed real-world dates (chosen because their weekday is a fixed
historical fact, not a moving target) rather than "today" at test-run
time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase

_NY = ZoneInfo("America/New_York")


def _freeze(monkeypatch: pytest.MonkeyPatch, when: datetime) -> None:
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            # Deliberately returns the base `datetime` type, not `cls`
            # (`_FrozenDatetime`) — LSP-unsound by design, since this
            # exists purely as test scaffolding to control what
            # `datetime.now()` returns inside the use case under test, not
            # as a real datetime subclass meant to be instantiated
            # elsewhere. Scoped to this test file only.
            return when if tz is None else when.astimezone(tz)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "src.application.market_data.get_market_status_use_case.datetime", _FrozenDatetime
    )


class TestGetMarketStatus:
    def test_open_during_regular_trading_hours(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 2026-01-06 is a Tuesday. 11:00 AM ET is well within 9:30-16:00.
        when = datetime(2026, 1, 6, 11, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.is_open is True
        assert result.session == "open"
        assert result.next_open is None

    def test_pre_market_before_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 7:00 AM ET on a Tuesday — before the 9:30 open.
        when = datetime(2026, 1, 6, 7, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.is_open is False
        assert result.session == "pre-market"
        assert result.next_open is not None

    def test_after_hours_past_close(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 5:00 PM ET on a Tuesday — after the 16:00 close.
        when = datetime(2026, 1, 6, 17, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.is_open is False
        assert result.session == "after-hours"

    def test_closed_on_weekend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 2026-01-10 is a Saturday.
        when = datetime(2026, 1, 10, 11, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.is_open is False
        assert result.session == "closed"

    def test_next_open_after_close_is_next_weekday_morning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Tuesday 5 PM ET -> next open should be Wednesday 9:30 AM ET.
        when = datetime(2026, 1, 6, 17, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.next_open is not None
        next_open_ny = result.next_open.astimezone(_NY)
        assert next_open_ny.date() == datetime(2026, 1, 7, tzinfo=_NY).date()
        assert next_open_ny.hour == 9
        assert next_open_ny.minute == 30

    def test_next_open_from_friday_evening_skips_to_monday(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 2026-01-09 is a Friday. 5 PM ET -> next open should be Monday.
        when = datetime(2026, 1, 9, 17, 0, tzinfo=_NY).astimezone(UTC)
        _freeze(monkeypatch, when)

        result = GetMarketStatusUseCase().execute()

        assert result.next_open is not None
        next_open_ny = result.next_open.astimezone(_NY)
        assert next_open_ny.weekday() == 0  # Monday
        assert next_open_ny.date() == datetime(2026, 1, 12, tzinfo=_NY).date()
