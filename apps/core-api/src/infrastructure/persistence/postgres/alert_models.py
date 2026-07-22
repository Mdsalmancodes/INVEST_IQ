"""SQLAlchemy declarative models for the alerts bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(alerts) and docs/architecture/05-data-pipeline-notifications-caching-monitoring.md
§12.2 (notifications, notification_preferences).

DISCLOSED SCOPE DECISION (documented here, not silently reduced — see also
tasks.py's module docstring for the evaluation-engine side of this same
decision): Document 5 §12.3 specifies alert-trigger delivery via Redis
Streams (`alerts:stream`, consumer group "notification-workers", `XCLAIM`
failover) into the `redis-broker` instance, with a dedicated resilience/
chaos test suite (Document 6 §16.2a). That resilience suite is explicitly
gated in the architecture's own text to "Phase 6 (real-time layer)" —
a LATER phase than this alerts work in the founder's actual build order —
and no WebSocket/Streams-consumer infrastructure exists anywhere in this
codebase yet. This phase persists triggered alerts directly to the
`notifications` table below (Document 5 §12.2, itself a fully-specified,
non-simplified part of the frozen architecture) instead of writing to a
Stream. Upgrade path: the evaluation engine's single
`NotificationRepository.save()` call is the only place that would change
to an `XADD` call when the real-time layer is built — no other code in
this bounded context depends on the delivery mechanism.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.postgres.models import Base


class AlertModel(Base):
    """Per Document 3 §8.1 `alerts` table — exact frozen DDL, no ADR
    needed (already includes the review-identified duplicate-alert
    UNIQUE constraint and the is_recurring/cooldown_minutes columns)."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "condition_type IN ('price_above','price_below','pct_change','rsi_threshold')",
            name="ck_alerts_condition_type",
        ),
        CheckConstraint("cooldown_minutes >= 0", name="ck_alerts_cooldown_non_negative"),
        UniqueConstraint(
            "user_id", "instrument_id", "condition_type", "threshold", name="uq_alerts_duplicate"
        ),
        Index(
            "idx_alerts_active_instrument",
            "instrument_id",
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    condition_type: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationModel(Base):
    """Per Document 5 §12.2 `notifications` table — exact frozen DDL.
    This is the DELIVERY mechanism this phase actually uses (see module
    docstring's disclosed scope decision)."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "idx_notifications_user_unread",
            "user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationPreferenceModel(Base):
    """Per Document 5 §12.2 `notification_preferences` table — exact
    frozen DDL. NOT wired into any use case's read path yet this phase
    (see verification report's disclosed-limitations section) — the
    columns exist and are persistable, but AlertEvaluationService does
    not yet consult quiet_hours/digest_frequency before creating a
    Notification row, since email/digest delivery itself is out of this
    phase's explicit scope (in-app notifications only)."""

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    price_alerts_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    price_alerts_push: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    digest_frequency: Mapped[str] = mapped_column(Text, nullable=False, server_default="daily")
    quiet_hours_start: Mapped[time | None] = mapped_column(Time())
    quiet_hours_end: Mapped[time | None] = mapped_column(Time())

    __table_args__ = (
        CheckConstraint(
            "digest_frequency IN ('off','daily','weekly')", name="ck_notification_prefs_digest"
        ),
    )
