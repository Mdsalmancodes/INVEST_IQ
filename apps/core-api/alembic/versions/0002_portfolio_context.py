"""create portfolio context tables

Revision ID: 0002_portfolio_context
Revises: 0001_identity_access
Create Date: 2026-07-22

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(instruments — minimal subset needed as FK target, see portfolio_models.py
module docstring; portfolios; holdings; transactions) and ADR-0003
(transactions.type extended with 'split','transfer_in','transfer_out' +
split_ratio/related_portfolio_id/cash_amount columns — additive only, no
existing column removed or retyped).

Written by hand against the verified SQLAlchemy models in
src/infrastructure/persistence/postgres/portfolio_models.py rather than via
`alembic revision --autogenerate` (requires a live Postgres connection,
unavailable in this environment — Docker not installed, Category D blocker
carried forward from Phase 1/2). Structurally verified: table names,
columns, and constraints below match portfolio_models.py exactly
(cross-checked line by line).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_portfolio_context"
down_revision: str | None = "0001_identity_access"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="USD"),
        sa.Column("ipo_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "asset_type IN ('equity','etf','index','crypto')", name="ck_instruments_asset_type"
        ),
        sa.UniqueConstraint("symbol", "exchange"),
    )
    op.create_index("idx_instruments_symbol", "instruments", ["symbol"])
    op.create_index(
        "idx_instruments_symbol_global",
        "instruments",
        ["symbol"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "portfolios",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_currency", sa.Text(), nullable=False, server_default="USD"),
        sa.Column("is_paper", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_portfolios_user", "portfolios", ["user_id"])

    op.create_table(
        "holdings",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_holdings_quantity_non_negative"),
        sa.CheckConstraint("average_cost >= 0", name="ck_holdings_average_cost_non_negative"),
        sa.UniqueConstraint("portfolio_id", "instrument_id"),
    )

    # Per ADR-0003: type CHECK extended with split/transfer_in/transfer_out;
    # split_ratio, related_portfolio_id, cash_amount are new nullable columns.
    op.create_table(
        "transactions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id"),
            nullable=True,  # nullable: deposit/withdrawal have no instrument
        ),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=True),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("fees", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("split_ratio", sa.Numeric(20, 8), nullable=True),  # ADR-0003
        sa.Column(
            "related_portfolio_id",  # ADR-0003
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id"),
            nullable=True,
        ),
        sa.Column("cash_amount", sa.Numeric(20, 8), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "type IN ('buy','sell','dividend','split','transfer_in','transfer_out',"
            "'deposit','withdrawal')",
            name="ck_transactions_type",
        ),
    )
    op.create_index(
        "idx_transactions_portfolio_time", "transactions", ["portfolio_id", "executed_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_transactions_portfolio_time", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("holdings")
    op.drop_index("idx_portfolios_user", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_index("idx_instruments_symbol_global", table_name="instruments")
    op.drop_index("idx_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
