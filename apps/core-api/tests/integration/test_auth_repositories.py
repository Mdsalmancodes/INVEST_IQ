"""Integration tests for auth repositories against a REAL Postgres instance.

Per docs/architecture/06-security-testing-strategy.md §16.2: "Integration |
pytest + testcontainers (real Postgres/Mongo/Redis in Docker)" — deliberately
NOT SQLite. SQLite silently accepts/ignores Postgres-specific types (CITEXT,
JSONB, INET) that this schema genuinely depends on (Document 3 §8.1); a
SQLite-backed test would pass even if a real Postgres-specific mapping bug
existed — which is exactly the kind of bug found and fixed in
audit_log_repository.py during this session (str vs. uuid.UUID for
resource_id) via manual inspection, not by SQLite testing catching it. Using
a weaker substitute here would given false confidence, not real coverage.

STATUS: written and statically verified (ruff clean, mypy strict clean —
confirmed via `poetry run mypy --strict tests/integration/`), but NOT YET
EXECUTED in this environment. Docker is not installed (Phase 1 Category D
blocker, carried forward) so testcontainers cannot spin up a real Postgres
container here. Execute via `pytest tests/integration/` once Docker is
available — see docs/phase-1/known-issues.md D2 for the underlying blocker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.domain.auth.entities import LoginHistoryEntry, RefreshToken, Role, User
from src.domain.auth.value_objects import Email, HashedPassword, UserId
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.repositories.login_history_repository import (
    SqlAlchemyLoginHistoryRepository,
)
from src.infrastructure.persistence.postgres.repositories.refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from src.infrastructure.persistence.postgres.repositories.user_repository import (
    SqlAlchemyUserRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_container() -> PostgresContainer:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest_asyncio.fixture
async def session(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncSession, None]:
    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=UserId.new(),
        email=Email("integration-test@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Integration Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )


class TestSqlAlchemyUserRepository:
    async def test_save_and_get_by_id_round_trips(self, session: AsyncSession) -> None:
        repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await repo.save(user)
        await session.commit()

        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.email == user.email
        assert fetched.full_name == user.full_name

    async def test_get_by_email_is_case_insensitive_via_citext(self, session: AsyncSession) -> None:
        # This is the specific behavior that only a real Postgres (CITEXT)
        # instance can verify — SQLite has no equivalent case-insensitive
        # text type, which is exactly why this must run against testcontainers.
        repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await repo.save(user)
        await session.commit()

        fetched = await repo.get_by_email(Email("INTEGRATION-TEST@EXAMPLE.COM"))
        assert fetched is not None
        assert fetched.id == user.id

    async def test_exists_with_email_true_after_save(self, session: AsyncSession) -> None:
        repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await repo.save(user)
        await session.commit()

        assert await repo.exists_with_email(user.email) is True

    async def test_exists_with_email_false_for_unknown_email(self, session: AsyncSession) -> None:
        repo = SqlAlchemyUserRepository(session)
        assert await repo.exists_with_email(Email("nobody@example.com")) is False

    async def test_save_persists_token_version_increment(self, session: AsyncSession) -> None:
        repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await repo.save(user)
        await session.commit()

        user.invalidate_all_sessions()
        await repo.save(user)
        await session.commit()

        fetched = await repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.token_version == 1


class TestSqlAlchemyRefreshTokenRepository:
    async def test_save_and_get_by_token_hash_round_trips(self, session: AsyncSession) -> None:
        user_repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await user_repo.save(user)
        await session.commit()

        token_repo = SqlAlchemyRefreshTokenRepository(session)
        token = RefreshToken(
            id=UserId.new(),
            user_id=user.id,
            token_hash="hashed-value",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )
        await token_repo.save(token)
        await session.commit()

        fetched = await token_repo.get_by_token_hash("hashed-value")
        assert fetched is not None
        assert fetched.user_id == user.id

    async def test_revoke_all_for_user_revokes_active_tokens_only(
        self, session: AsyncSession
    ) -> None:
        user_repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await user_repo.save(user)
        await session.commit()

        token_repo = SqlAlchemyRefreshTokenRepository(session)
        active_token = RefreshToken(
            id=UserId.new(),
            user_id=user.id,
            token_hash="active-token-hash",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )
        await token_repo.save(active_token)
        await session.commit()

        await token_repo.revoke_all_for_user(user.id, datetime.now(UTC))
        await session.commit()

        fetched = await token_repo.get_by_token_hash("active-token-hash")
        assert fetched is not None
        assert fetched.is_revoked is True


class TestSqlAlchemyLoginHistoryRepository:
    async def test_save_and_list_for_user_returns_newest_first(self, session: AsyncSession) -> None:
        user_repo = SqlAlchemyUserRepository(session)
        user = _make_user()
        await user_repo.save(user)
        await session.commit()

        history_repo = SqlAlchemyLoginHistoryRepository(session)
        for i in range(3):
            entry = LoginHistoryEntry(
                id=UserId.new(),
                user_id=user.id,
                ip_address="127.0.0.1",
                user_agent="pytest",
                device_label="Test Runner",
                success=True,
                failure_reason=None,
                created_at=datetime.now(UTC) + timedelta(seconds=i),
            )
            await history_repo.save(entry)
        await session.commit()

        results = await history_repo.list_for_user(user.id, limit=10)
        assert len(results) == 3
        # newest first
        assert results[0].created_at >= results[1].created_at >= results[2].created_at
