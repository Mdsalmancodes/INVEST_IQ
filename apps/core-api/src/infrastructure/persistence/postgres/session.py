"""Async SQLAlchemy engine/session setup for Postgres.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §19.4:
async DB drivers throughout (asyncpg), connection pooling sized per service
replica count — using SQLAlchemy's own async engine and pooling rather than
custom connection management, per the "use SQLAlchemy properly" directive.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        str(settings.database_url),
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,  # avoids serving requests against a dead connection
        echo=False,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async session.

    Per Document 3 §7.7's read-after-write consistency rule: this session is
    bound to the primary. Read-replica routing (when introduced) will be a
    distinct dependency (e.g. get_read_replica_session), never a silent
    fallback from this one, so call sites are explicit about which they need.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
