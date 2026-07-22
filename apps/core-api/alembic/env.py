"""Alembic environment — reads DATABASE_URL from core-api's own Settings
(src.config) so there is exactly one source of truth for the connection
string, never a second hardcoded one duplicated into alembic.ini.

Per Document 3 §8.1: the first real migration (Phase 2) creates the identity
& access tables (users, oauth_accounts, refresh_tokens, audit_logs). This
file is scaffolding only — no migrations exist yet in Phase 1.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from src.config import get_settings

# Phase 2 onward: import each bounded context's SQLAlchemy declarative Base
# here so `alembic revision --autogenerate` can detect model changes.
from src.infrastructure.persistence.postgres.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
