"""create alerts and notifications context tables

Revision ID: 0005_alerts_context
Revises: 0004_watchlist_context
Create Date: 2026-07-22

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(alerts — exact frozen DDL, no ADR needed) and
docs/architecture/05-data-pipeline-notifications-caching-monitoring.md
§12.2 (notifications, notification_preferences — exact frozen DDL).

DISCLOSED SCOPE DECISION: see alert_models.py's module docstring for the
full rationale — this phase persists triggered alerts to `notifications`
(built here) rather than a Redis Stream, since the Redis-Streams/WebSocket
real-time layer and its mandated resilience test suite are architecturally
gated to a later phase than this alerts work.

Written by hand against the verified SQLAlchemy models in
src/infrastructure/persistence/postgres/alert_models.py rather than via
`alembic revision --autogenerate` (requires a live Postgres connection,
unavailable in this environment — Docker not installed, Category D blocker
carried forward from Phase 1). Structurally verified: table names, columns,
and constraints below match alert_models.py exactly (cross-checked line by
line).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_alerts_context"
down_revision: str | None = "0004_watchlist_context"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("condition_type", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Numeric(20, 8), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "condition_type IN ('price_above','price_below','pct_change','rsi_threshold')",
            name="ck_alerts_condition_type",
        ),
        sa.CheckConstraint("cooldown_minutes >= 0", name="ck_alerts_cooldown_non_negative"),
        sa.UniqueConstraint(
            "user_id", "instrument_id", "condition_type", "threshold", name="uq_alerts_duplicate"
        ),
    )
    op.create_index(
        "idx_alerts_active_instrument",
        "alerts",
        ["instrument_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_notifications_user_unread",
        "notifications",
        ["user_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("price_alerts_email", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("price_alerts_push", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("digest_frequency", sa.Text(), nullable=False, server_default="daily"),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.CheckConstraint(
            "digest_frequency IN ('off','daily','weekly')", name="ck_notification_prefs_digest"
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("idx_notifications_user_unread", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("idx_alerts_active_instrument", table_name="alerts")
    op.drop_table("alerts")
