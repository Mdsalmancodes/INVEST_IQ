"""Domain entities for the notifications bounded context.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md
§12.2 (notifications, notification_preferences — exact frozen DDL) and
alert_models.py's module docstring for the disclosed scope decision
(triggered alerts persist to `notifications`, not a Redis Stream, since
the real-time layer is a later phase).

Two entities live here, matching the two tables this bounded context
persists to. Neither is an aggregate root with owned children (unlike
Watchlist) — both are simple entities, matching Alert's style for this
same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Literal

from src.domain.notifications.exceptions import InvalidDigestFrequencyError
from src.domain.notifications.value_objects import NotificationId

NotificationType = Literal["alert_triggered", "system", "digest"]
DigestFrequency = Literal["off", "daily", "weekly"]

VALID_DIGEST_FREQUENCIES: frozenset[str] = frozenset({"off", "daily", "weekly"})


@dataclass(slots=True)
class Notification:
    """An in-app notification delivered to a user. `mark_as_read()` is the
    only mutation this entity exposes — notifications are otherwise
    immutable once created (Document 5 §12.2), matching how AlertModel's
    `triggered_at` is a one-way clock, never edited after the fact."""

    id: NotificationId
    user_id: str
    type: NotificationType
    title: str
    body: str
    metadata: dict[str, object]
    read_at: datetime | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        user_id: str,
        type: NotificationType,
        title: str,
        body: str,
        metadata: dict[str, object] | None = None,
    ) -> Notification:
        return cls(
            id=NotificationId.new(),
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            metadata=metadata or {},
            read_at=None,
            created_at=datetime.now(UTC),
        )

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_as_read(self) -> None:
        """Idempotent — marking an already-read notification as read again
        does not change its original read_at timestamp, matching how
        Alert.trigger() on an already-triggered non-recurring alert would
        never be called twice by well-behaved application code, but this
        entity defends against it anyway since "double-click mark as
        read" is a realistic UI race, unlike alert triggering."""
        if self.read_at is None:
            self.read_at = datetime.now(UTC)


@dataclass(slots=True)
class NotificationPreferences:
    """Per-user notification delivery preferences (Document 5 §12.2).
    Primary-keyed by user_id (1:1 with User, not a separate UUID id) —
    matches the DB table's own primary key exactly, so no separate
    NotificationPreferencesId value object is introduced."""

    user_id: str
    price_alerts_email: bool
    price_alerts_push: bool
    digest_frequency: DigestFrequency
    quiet_hours_start: time | None = field(default=None)
    quiet_hours_end: time | None = field(default=None)

    @classmethod
    def create_default(cls, user_id: str) -> NotificationPreferences:
        """Matches the DB columns' own server_default values exactly
        (migration 0005_alerts_context.py) — used when a user has no
        notification_preferences row yet, so GetPreferences never 404s."""
        return cls(
            user_id=user_id,
            price_alerts_email=True,
            price_alerts_push=True,
            digest_frequency="daily",
            quiet_hours_start=None,
            quiet_hours_end=None,
        )

    def update(
        self,
        price_alerts_email: bool | None = None,
        price_alerts_push: bool | None = None,
        digest_frequency: DigestFrequency | None = None,
        quiet_hours_start: time | None = None,
        quiet_hours_end: time | None = None,
        clear_quiet_hours: bool = False,
    ) -> None:
        if price_alerts_email is not None:
            self.price_alerts_email = price_alerts_email
        if price_alerts_push is not None:
            self.price_alerts_push = price_alerts_push
        if digest_frequency is not None:
            _validate_digest_frequency(digest_frequency)
            self.digest_frequency = digest_frequency
        if clear_quiet_hours:
            self.quiet_hours_start = None
            self.quiet_hours_end = None
        else:
            if quiet_hours_start is not None:
                self.quiet_hours_start = quiet_hours_start
            if quiet_hours_end is not None:
                self.quiet_hours_end = quiet_hours_end


def _validate_digest_frequency(digest_frequency: str) -> None:
    if digest_frequency not in VALID_DIGEST_FREQUENCIES:
        raise InvalidDigestFrequencyError(
            f"Invalid digest_frequency {digest_frequency!r}; must be one of "
            f"{sorted(VALID_DIGEST_FREQUENCIES)}"
        )
