"""Async SQLAlchemy engine/session setup for Postgres.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §19.4:
async DB drivers throughout (asyncpg), connection pooling sized per service
replica count — using SQLAlchemy's own async engine and pooling rather than
custom connection management, per the "use SQLAlchemy properly" directive.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
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

    Commits on successful request completion, rolls back on any exception —
    repositories only ever call session.flush() (never commit()), so without
    this the transaction is implicitly rolled back when the `async with`
    block below exits, silently discarding every write in the application.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_committing_session_scope() -> AsyncIterator[AsyncSession]:
    """Same commit-on-success/rollback-on-exception semantics as
    get_db_session, but as a plain async context manager rather than a
    FastAPI dependency generator — for the Phase 9 realtime background
    services (main.py's `session_scope=` callable), which run outside any
    request lifecycle and so cannot use FastAPI's Depends() machinery.

    Without this, those services' repositories (which only ever call
    session.flush(), never commit()) would silently discard every write —
    e.g. the Alert Evaluation Engine's Alert.trigger() — the same bug
    get_db_session fixes for the request path.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
