"""create watchlist context tables

Revision ID: 0004_watchlist_context
Revises: 0003_market_data
Create Date: 2026-07-22

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(watchlists, watchlist_items) and ADR-0004 (additive columns: is_default +
updated_at on watchlists; position + is_pinned on watchlist_items — no
existing column removed or retyped; at-most-one-default-per-user enforced
via a partial unique index, mirroring idx_instruments_symbol_global's
established pattern).

Written by hand against the verified SQLAlchemy models in
src/infrastructure/persistence/postgres/watchlist_models.py rather than via
`alembic revision --autogenerate` (requires a live Postgres connection,
unavailable in this environment — Docker not installed, Category D blocker
carried forward from Phase 1/2). Structurally verified: table names,
columns, and constraints below match watchlist_models.py exactly
(cross-checked line by line).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_watchlist_context"
down_revision: str | None = "0003_market_data"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
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
        sa.Column("name", sa.Text(), nullable=False, server_default="My Watchlist"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),  # ADR-0004
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(  # ADR-0004
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_watchlists_user", "watchlists", ["user_id"])
    op.create_index(  # ADR-0004: at most one default watchlist per user
        "idx_watchlists_user_default",
        "watchlists",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    op.create_table(
        "watchlist_items",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "watchlist_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),  # ADR-0004
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),  # ADR-0004
        sa.Column(
            "added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("watchlist_id", "instrument_id"),
    )
    op.create_index(
        "idx_watchlist_items_watchlist_position", "watchlist_items", ["watchlist_id", "position"]
    )


def downgrade() -> None:
    op.drop_index("idx_watchlist_items_watchlist_position", table_name="watchlist_items")
    op.drop_table("watchlist_items")
    op.drop_index("idx_watchlists_user_default", table_name="watchlists")
    op.drop_index("idx_watchlists_user", table_name="watchlists")
    op.drop_table("watchlists")
