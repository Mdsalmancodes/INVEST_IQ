"""Integration tests for the watchlist repository against a REAL Postgres
instance.

Per docs/architecture/06-security-testing-strategy.md §16.2 (testcontainers,
not SQLite) — same rationale as test_market_data_repositories.py and
test_portfolio_repositories.py. For the watchlist context specifically, a
real Postgres is essential to verify: the idx_watchlists_user_default
partial unique index actually enforces "at most one default watchlist per
user" (ADR-0004) at the database level (not just application-layer trust),
the UNIQUE(watchlist_id, instrument_id) constraint on watchlist_items, ON
DELETE CASCADE from watchlists to watchlist_items, and that
SqlAlchemyWatchlistRepository.save()'s delete-orphaned-items logic
actually removes rows from the database, not just the in-memory aggregate.

A real User row is created for each test needing a watchlist (via
SqlAlchemyUserRepository, matching test_portfolio_repositories.py's exact
pattern) since watchlists.user_id is a genuine FK to users(id) — a raw
insert with an arbitrary UUID would fail on the FK constraint before ever
reaching the partial-unique-index behavior under test.

STATUS: written and statically verified (ruff clean, mypy strict clean),
but NOT YET EXECUTED in this environment. Docker is not installed (Category
D blocker, carried forward through Phases 1-4). Execute via
`pytest tests/integration/` once Docker is available.
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
from src.domain.market_data.entities import AssetType, Instrument
from src.domain.market_data.value_objects import InstrumentId as MarketDataInstrumentId
from src.domain.watchlist.entities import Watchlist
from src.domain.watchlist.repositories import WatchlistListFilter
from src.domain.watchlist.value_objects import InstrumentId
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.user_repository import (
    SqlAlchemyUserRepository,
)
from src.infrastructure.persistence.postgres.repositories.watchlist_repository import (
    SqlAlchemyWatchlistRepository,
)
from src.infrastructure.persistence.postgres.watchlist_models import (
    WatchlistItemModel,
    WatchlistModel,
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
        email=Email(f"watchlist-test-{uuid.uuid4()}@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Watchlist Test User",
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


class TestSqlAlchemyWatchlistRepository:
    async def test_save_and_get_by_id_round_trips(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyWatchlistRepository(session)
        watchlist = Watchlist.create(user_id=str(user_id), name="My Watchlist")
        await repo.save(watchlist)
        await session.commit()

        fetched = await repo.get_by_id(watchlist.id)
        assert fetched is not None
        assert fetched.name == "My Watchlist"
        assert fetched.items == []

    async def test_save_persists_items_and_round_trips(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "WLTEST1")

        repo = SqlAlchemyWatchlistRepository(session)
        watchlist = Watchlist.create(user_id=str(user_id), name="Watchlist")
        watchlist.add_item(instrument_id)
        await repo.save(watchlist)
        await session.commit()

        fetched = await repo.get_by_id(watchlist.id)
        assert fetched is not None
        assert len(fetched.items) == 1
        assert fetched.items[0].instrument_id == instrument_id

    async def test_removing_an_item_and_saving_deletes_the_row(self, session: AsyncSession) -> None:
        # Verifies SqlAlchemyWatchlistRepository.save()'s delete-orphaned-
        # items logic actually removes the row from Postgres, not just the
        # in-memory aggregate — a fake dict-backed repository could never
        # catch a missing DELETE statement here.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "WLTEST2")

        repo = SqlAlchemyWatchlistRepository(session)
        watchlist = Watchlist.create(user_id=str(user_id), name="Watchlist")
        item = watchlist.add_item(instrument_id)
        await repo.save(watchlist)
        await session.commit()

        watchlist.remove_item(item.id)
        await repo.save(watchlist)
        await session.commit()

        fetched = await repo.get_by_id(watchlist.id)
        assert fetched is not None
        assert fetched.items == []

    async def test_duplicate_instrument_violates_unique_constraint(
        self, session: AsyncSession
    ) -> None:
        # Verifies UNIQUE(watchlist_id, instrument_id) is a real Postgres
        # constraint (Document 3 §8.1), not just the domain layer's
        # add_item() check.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "WLTEST3")

        repo = SqlAlchemyWatchlistRepository(session)
        watchlist = Watchlist.create(user_id=str(user_id), name="Watchlist")
        watchlist.add_item(instrument_id)
        await repo.save(watchlist)
        await session.commit()

        duplicate = WatchlistItemModel(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id.value,
            instrument_id=instrument_id.value,
            position=99,
            is_pinned=False,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_deleting_watchlist_cascades_to_items(self, session: AsyncSession) -> None:
        # Verifies ON DELETE CASCADE from watchlists to watchlist_items
        # (Document 3 §8.1) actually works at the database level.
        user_id = await _make_user(session)
        instrument_id = await _make_instrument(session, "WLTEST4")

        repo = SqlAlchemyWatchlistRepository(session)
        watchlist = Watchlist.create(user_id=str(user_id), name="Watchlist")
        watchlist.add_item(instrument_id)
        await repo.save(watchlist)
        await session.commit()

        await repo.delete(watchlist.id)
        await session.commit()

        remaining_items = await session.execute(
            text("SELECT COUNT(*) FROM watchlist_items WHERE watchlist_id = :wid"),
            {"wid": watchlist.id.value},
        )
        assert remaining_items.scalar_one() == 0

    async def test_default_watchlist_partial_unique_index_enforced(
        self, session: AsyncSession
    ) -> None:
        # Verifies idx_watchlists_user_default (ADR-0004) actually
        # enforces "at most one default watchlist per user" at the
        # database level — a fake in-memory repository's application-layer
        # demotion logic (CreateWatchlistUseCase/UpdateWatchlistUseCase)
        # could never catch a real constraint violation like this; this
        # test deliberately bypasses that application-layer logic via a
        # raw second insert to prove the DB-level invariant holds
        # independently of it.
        user_id = await _make_user(session)
        repo = SqlAlchemyWatchlistRepository(session)
        first = Watchlist.create(user_id=str(user_id), name="First", is_default=True)
        await repo.save(first)
        await session.commit()

        session.add(
            WatchlistModel(
                id=uuid.uuid4(),
                user_id=user_id.value,
                name="Second",
                is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_list_for_user_search_and_pagination(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyWatchlistRepository(session)
        await repo.save(Watchlist.create(user_id=str(user_id), name="Tech Stocks"))
        await repo.save(Watchlist.create(user_id=str(user_id), name="Energy"))
        await session.commit()

        result = await repo.list_for_user(
            str(user_id), WatchlistListFilter(search="tech", page=1, page_size=20)
        )
        assert result.total_count == 1
        assert result.items[0].name == "Tech Stocks"

    async def test_get_default_for_user_returns_none_when_no_default(
        self, session: AsyncSession
    ) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyWatchlistRepository(session)
        await repo.save(Watchlist.create(user_id=str(user_id), name="Watchlist"))
        await session.commit()

        assert await repo.get_default_for_user(str(user_id)) is None

    async def test_count_for_user(self, session: AsyncSession) -> None:
        user_id = await _make_user(session)
        repo = SqlAlchemyWatchlistRepository(session)
        await repo.save(Watchlist.create(user_id=str(user_id), name="One"))
        await repo.save(Watchlist.create(user_id=str(user_id), name="Two"))
        await session.commit()

        assert await repo.count_for_user(str(user_id)) == 2
