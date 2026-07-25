"""Integration tests for the notification repositories against a REAL
Postgres instance.

Per docs/architecture/06-security-testing-strategy.md §16.2 (testcontainers,
not SQLite) — same rationale as test_alert_repositories.py. For the
notifications context specifically, a real Postgres is essential to
verify: the ck_notification_prefs_digest CHECK constraint actually rejects
an invalid digest_frequency at the database level, ON DELETE CASCADE from
users to notifications and notification_preferences, the
idx_notifications_user_unread partial index actually narrows queries
correctly, and mark_all_as_read_for_user()'s bulk UPDATE actually persists
to the database (a fake in-memory repository's loop-and-save could never
catch a missing/incorrect UPDATE statement).

STATUS: written and statically verified (ruff clean, mypy strict clean),
but NOT YET EXECUTED in this environment. Docker is not installed (Category
D blocker, carried forward through Phases 1-5). Execute via
`pytest tests/integration/ -m integration` once Docker is available.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.domain.auth.entities import Role, User
from src.domain.auth.value_objects import Email, HashedPassword
from src.domain.auth.value_objects import UserId as AuthUserId
from src.domain.notifications.entities import Notification, NotificationPreferences
from src.domain.notifications.repositories import NotificationListFilter
from src.infrastructure.persistence.postgres.alert_models import NotificationPreferenceModel
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.repositories.notification_preference_repository import (  # noqa: E501
    SqlAlchemyNotificationPreferenceRepository,
)
from src.infrastructure.persistence.postgres.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
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


async def _make_user(session: AsyncSession) -> AuthUserId:
    now = datetime.now(UTC)
    user = User(
        id=AuthUserId.new(),
        email=Email(f"notif-test-{uuid.uuid4()}@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Notifications Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyUserRepository(session).save(user)
    await session.commit()
    return user.id


class TestSqlAlchemyNotificationRepository:
    async def test_save_and_get_by_id_round_trips(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationRepository(session)
        notification = Notification.create(
            user_id=str(user_id),
            type="alert_triggered",
            title="AAPL crossed $150",
            body="Your price alert triggered.",
            metadata={"symbol": "AAPL"},
        )
        await repo.save(notification)
        await session.commit()

        fetched = await repo.get_by_id(notification.id)
        assert fetched is not None
        assert fetched.title == "AAPL crossed $150"
        assert fetched.metadata == {"symbol": "AAPL"}

    async def test_deleting_user_cascades_to_notifications(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationRepository(session)
        notification = Notification.create(
            user_id=str(user_id), type="system", title="Welcome", body="body"
        )
        await repo.save(notification)
        await session.commit()

        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id.value})
        await session.commit()

        remaining = await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE id = :nid"),
            {"nid": notification.id.value},
        )
        assert remaining.scalar_one() == 0

    async def test_list_for_user_unread_only_and_unread_count(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationRepository(session)
        unread = Notification.create(
            user_id=str(user_id), type="system", title="Unread", body="u"
        )
        read = Notification.create(user_id=str(user_id), type="system", title="Read", body="r")
        read.mark_as_read()
        await repo.save(unread)
        await repo.save(read)
        await session.commit()

        result = await repo.list_for_user(
            str(user_id), NotificationListFilter(unread_only=True, page=1, page_size=20)
        )
        assert result.total_count == 1
        assert result.items[0].id == unread.id
        assert result.unread_count == 1

    async def test_mark_all_as_read_for_user_updates_all_rows(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationRepository(session)
        await repo.save(
            Notification.create(user_id=str(user_id), type="system", title="A", body="a")
        )
        await repo.save(
            Notification.create(user_id=str(user_id), type="system", title="B", body="b")
        )
        await session.commit()

        count = await repo.mark_all_as_read_for_user(str(user_id))
        await session.commit()

        assert count == 2
        result = await repo.list_for_user(
            str(user_id), NotificationListFilter(unread_only=True, page=1, page_size=20)
        )
        assert result.total_count == 0


class TestSqlAlchemyNotificationPreferenceRepository:
    async def test_save_and_get_by_user_id_round_trips(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationPreferenceRepository(session)
        preferences = NotificationPreferences.create_default(str(user_id))
        preferences.update(digest_frequency="weekly")

        await repo.save(preferences)
        await session.commit()

        fetched = await repo.get_by_user_id(str(user_id))
        assert fetched is not None
        assert fetched.digest_frequency == "weekly"

    async def test_get_by_user_id_returns_none_when_not_stored(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationPreferenceRepository(session)
        assert await repo.get_by_user_id(str(user_id)) is None

    async def test_invalid_digest_frequency_violates_check_constraint(
        self, session: AsyncSession
    ) -> None:
        # Verifies ck_notification_prefs_digest actually rejects an
        # invalid value at the database level — the domain layer's own
        # _validate_digest_frequency() would never let this construct in
        # normal use, so this deliberately bypasses it via a raw model
        # insert to prove the DB-level invariant holds independently.
        user_id = await _make_user(session)
        session.add(
            NotificationPreferenceModel(user_id=user_id.value, digest_frequency="hourly")
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_deleting_user_cascades_to_preferences(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyNotificationPreferenceRepository(session)
        await repo.save(NotificationPreferences.create_default(str(user_id)))
        await session.commit()

        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id.value})
        await session.commit()

        remaining = await session.execute(
            text("SELECT COUNT(*) FROM notification_preferences WHERE user_id = :uid"),
            {"uid": user_id.value},
        )
        assert remaining.scalar_one() == 0
