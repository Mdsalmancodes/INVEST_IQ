"""create market data tables

Revision ID: 0003_market_data
Revises: 0002_portfolio_context
Create Date: 2026-07-22

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(ohlcv_bars, corporate_actions). `instruments` already exists as of
migration 0002_portfolio_context (created in Phase 3 as a minimal
FK-target subset of this same frozen table) — not recreated here.

DISCLOSED SIMPLIFICATION (Phase 4, founder-approved scope): the frozen DDL
specifies `ohlcv_bars` as natively RANGE-partitioned by `bar_time` with a
scheduled monthly partition-creation maintenance job. That maintenance job
is not built in this phase (not in the founder's explicit Phase 4 list) —
`ohlcv_bars` is created here as a normal (non-partitioned) table. Upgrade
path: partitioning can be added via a future migration (`ALTER TABLE ...
PARTITION BY RANGE` requires a table rebuild in Postgres, but the read/
write path is entirely encapsulated behind OhlcvBarRepository, so no
application code changes when that migration lands. See
docs/phase-4/verification-report.md for the disclosure.

Written by hand against the verified SQLAlchemy models in
src/infrastructure/persistence/postgres/market_data_models.py rather than
via `alembic revision --autogenerate` (requires a live Postgres connection,
unavailable in this environment — Docker not installed, Category D
blocker carried forward from Phase 1/2/3). Structurally verified: table
names, columns, and constraints below match market_data_models.py exactly
(cross-checked line by line).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_market_data"
down_revision: str | None = "0002_portfolio_context"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "ohlcv_bars",
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            primary_key=True,
        ),
        sa.Column("interval", sa.Text(), primary_key=True),
        sa.Column("bar_time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("adjusted_close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "interval IN ('1min','5min','15min','1h','1d','1w')", name="ck_ohlcv_bars_interval"
        ),
        sa.CheckConstraint("volume >= 0", name="ck_ohlcv_bars_volume_non_negative"),
    )
    op.create_index(
        "idx_ohlcv_bars_instrument_interval_time",
        "ohlcv_bars",
        ["instrument_id", "interval", sa.text("bar_time DESC")],
    )

    op.create_table(
        "corporate_actions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("ratio", sa.Numeric(20, 8), nullable=True),
        sa.Column("cash_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action_type IN ('split','dividend','spinoff')", name="ck_corporate_actions_type"
        ),
        sa.UniqueConstraint("instrument_id", "action_type", "ex_date"),
    )
    op.create_index(
        "idx_corporate_actions_instrument_exdate",
        "corporate_actions",
        ["instrument_id", sa.text("ex_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_corporate_actions_instrument_exdate", table_name="corporate_actions")
    op.drop_table("corporate_actions")
    op.drop_index("idx_ohlcv_bars_instrument_interval_time", table_name="ohlcv_bars")
    op.drop_table("ohlcv_bars")
