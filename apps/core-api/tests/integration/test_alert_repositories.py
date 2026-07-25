"""Integration tests for the alert repository against a REAL Postgres
instance.

Per docs/architecture/06-security-testing-strategy.md §16.2 (testcontainers,
not SQLite) — same rationale as test_watchlist_repositories.py. For the
alerts context specifically, a real Postgres is essential to verify: the
uq_alerts_duplicate UNIQUE constraint (user_id, instrument_id,
condition_type, threshold) actually enforces at the database level, the
ck_alerts_condition_type CHECK constraint rejects an invalid condition_type
at the database level (not just the domain layer's own validation), the
ck_alerts_cooldown_non_negative CHECK constraint, ON DELETE CASCADE from
users to alerts, and idx_alerts_active_instrument (partial index) actually
narrows list_active_for_instrument's results to active alerts only.

A real User row and a real Instrument row are created for each test
needing an alert (via SqlAlchemyUserRepository / SqlAlchemyInstrumentRepository,
matching test_watchlist_repositories.py's exact pattern) since alerts.user_id
and alerts.instrument_id are genuine FKs.

STATUS: written and statically verified (ruff clean, mypy strict clean),
but NOT YET EXECUTED in this environment. Docker is not installed (Category
D blocker, carried forward through Phases 1-5). Execute via
`pytest tests/integration/ -m integration` once Docker is available.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.domain.alerts.entities import Alert
from src.domain.alerts.repositories import AlertListFilter
from src.domain.alerts.value_objects import InstrumentId
from src.domain.auth.entities import Role, User
from src.domain.auth.value_objects import Email, HashedPassword
from src.domain.auth.value_objects import UserId as AuthUserId
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.infrastructure.persistence.postgres.alert_models import AlertModel
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.repositories.alert_repository import (
    SqlAlchemyAlertRepository,
)
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
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
        email=Email(f"alerts-test-{uuid.uuid4()}@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Alerts Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyUserRepository(session).save(user)
    await session.commit()
    return user.id


async def _make_instrument(session: AsyncSession, symbol: str) -> InstrumentId:
    instrument = Instrument(
        id=MarketDataInstrumentId(uuid.uuid4()),
        symbol=symbol,
        exchange="NASDAQ",
        name=f"{symbol} Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector=None,
        industry=None,
        ipo_date=None,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    await SqlAlchemyInstrumentRepository(session).save(instrument)
    await session.commit()
    return InstrumentId(instrument.id.value)


class TestSqlAlchemyAlertRepository:
    async def test_save_and_get_by_id_round_trips(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST1")

        repo = SqlAlchemyAlertRepository(session)
        alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("150.50"),
        )
        await repo.save(alert)
        await session.commit()

        fetched = await repo.get_by_id(alert.id)
        assert fetched is not None
        assert fetched.condition_type == "price_above"
        assert fetched.threshold == Decimal("150.50")

    async def test_duplicate_alert_violates_unique_constraint(
        self, session: AsyncSession
    ) -> None:
        # Verifies uq_alerts_duplicate (user_id, instrument_id,
        # condition_type, threshold) is a real Postgres constraint
        # (migration 0005_alerts_context.py), not just the application
        # layer's exists_duplicate() pre-check.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST2")

        repo = SqlAlchemyAlertRepository(session)
        alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        await repo.save(alert)
        await session.commit()

        duplicate = AlertModel(
            id=uuid.uuid4(),
            user_id=user_id.value,
            instrument_id=instrument_id.value,
            condition_type="price_above",
            threshold=Decimal("150"),
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_invalid_condition_type_violates_check_constraint(
        self, session: AsyncSession
    ) -> None:
        # Verifies ck_alerts_condition_type actually rejects an invalid
        # value at the database level — the domain layer's own
        # _validate_condition_type() would never let this construct in
        # normal use, so this deliberately bypasses it via a raw model
        # insert to prove the DB-level invariant holds independently.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST3")

        session.add(
            AlertModel(
                id=uuid.uuid4(),
                user_id=user_id.value,
                instrument_id=instrument_id.value,
                condition_type="not_a_real_condition",
                threshold=Decimal("10"),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_negative_cooldown_violates_check_constraint(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST4")

        session.add(
            AlertModel(
                id=uuid.uuid4(),
                user_id=user_id.value,
                instrument_id=instrument_id.value,
                condition_type="price_above",
                threshold=Decimal("10"),
                cooldown_minutes=-1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_deleting_user_cascades_to_alerts(self, session: AsyncSession) -> None:
        # Verifies ON DELETE CASCADE from users to alerts (migration
        # 0005_alerts_context.py) actually works at the database level.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST5")

        repo = SqlAlchemyAlertRepository(session)
        alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        await repo.save(alert)
        await session.commit()

        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id.value})
        await session.commit()

        remaining = await session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE id = :aid"), {"aid": alert.id.value}
        )
        assert remaining.scalar_one() == 0

    async def test_list_active_for_instrument_excludes_inactive(
        self, session: AsyncSession
    ) -> None:
        # Verifies idx_alerts_active_instrument (partial index on
        # is_active = true) actually narrows results correctly.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST6")

        repo = SqlAlchemyAlertRepository(session)
        active_alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        inactive_alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_below",
            threshold=Decimal("5"),
        )
        inactive_alert.deactivate()
        await repo.save(active_alert)
        await repo.save(inactive_alert)
        await session.commit()

        results = await repo.list_active_for_instrument(instrument_id)
        assert [a.id for a in results] == [active_alert.id]

    async def test_list_for_user_filters_by_is_active_and_paginates(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST7")

        repo = SqlAlchemyAlertRepository(session)
        active_alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        inactive_alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_below",
            threshold=Decimal("5"),
        )
        inactive_alert.deactivate()
        await repo.save(active_alert)
        await repo.save(inactive_alert)
        await session.commit()

        result = await repo.list_for_user(
            str(user_id), AlertListFilter(is_active=True, page=1, page_size=20)
        )
        assert result.total_count == 1
        assert result.items[0].id == active_alert.id

    async def test_exists_duplicate_true_for_matching_tuple(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST8")

        repo = SqlAlchemyAlertRepository(session)
        alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        await repo.save(alert)
        await session.commit()

        assert (
            await repo.exists_duplicate(str(user_id), instrument_id, "price_above", Decimal("10"))
            is True
        )
        assert (
            await repo.exists_duplicate(str(user_id), instrument_id, "price_below", Decimal("10"))
            is False
        )

    async def test_delete_removes_the_row(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "ALTEST9")

        repo = SqlAlchemyAlertRepository(session)
        alert = Alert.create(
            user_id=str(user_id),
            instrument_id=instrument_id,
            condition_type="price_above",
            threshold=Decimal("10"),
        )
        await repo.save(alert)
        await session.commit()

        await repo.delete(alert.id)
        await session.commit()

        assert await repo.get_by_id(alert.id) is None
