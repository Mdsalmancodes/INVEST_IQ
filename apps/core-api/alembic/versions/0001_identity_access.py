"""create identity and access tables

Revision ID: 0001_identity_access
Revises:
Create Date: 2026-07-22

Per docs/architecture/03-backend-architecture-database-design.md §8.1
(users, oauth_accounts, refresh_tokens, audit_logs) and ADR-0002
(login_history). Written by hand against the verified SQLAlchemy models in
src/infrastructure/persistence/postgres/models.py rather than via
`alembic revision --autogenerate` (which requires a live Postgres connection,
unavailable in this environment — Docker not installed, per Phase 1's
documented Category D blocker). Structurally verified: table names, columns,
and constraints below match models.py exactly (cross-checked line by line).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_identity_access"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # CITEXT extension required for case-insensitive email uniqueness (Document 3 §8.1)
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.dialects.postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="user"),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_profile", sa.Text(), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role IN ('user','pro_user','admin','super_admin')", name="ck_users_role"
        ),
        sa.CheckConstraint(
            "risk_profile IN ('conservative','moderate','aggressive')",
            name="ck_users_risk_profile",
        ),
    )

    op.create_table(
        "oauth_accounts",
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
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("provider", "provider_user_id"),
    )

    op.create_table(
        "refresh_tokens",
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
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_refresh_tokens_user",
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=True),
        sa.Column("resource_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_address", sa.dialects.postgresql.INET(), nullable=True),
        sa.Column(
            "metadata",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_audit_logs_user_time", "audit_logs", ["user_id", sa.text("created_at DESC")]
    )

    # Per ADR-0002
    op.create_table(
        "login_history",
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
        sa.Column("ip_address", sa.dialects.postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_label", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_login_history_user_time", "login_history", ["user_id", sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("login_history")
    op.drop_index("idx_audit_logs_user_time", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("idx_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("oauth_accounts")
    op.drop_table("users")
