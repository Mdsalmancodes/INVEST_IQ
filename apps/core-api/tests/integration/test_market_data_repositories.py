"""Integration tests for market_data repositories against a REAL Postgres
instance.

Per docs/architecture/06-security-testing-strategy.md §16.2 (testcontainers,
not SQLite) — same rationale as tests/integration/test_portfolio_repositories.py.
For the market_data context specifically, a real Postgres is essential to
verify: the `ck_ohlcv_bars_interval` and `ck_corporate_actions_type` CHECK
constraints actually accept/reject the right values, the composite primary
key (instrument_id, interval, bar_time) on ohlcv_bars enforces the upsert
semantics save_many() depends on (ON CONFLICT DO UPDATE), the
UNIQUE(instrument_id, action_type, ex_date) constraint on corporate_actions,
and the idx_instruments_symbol_global partial unique index actually
resolves get_by_symbol() correctly.

STATUS: written and statically verified (ruff clean, mypy strict clean),
but NOT YET EXECUTED in this environment. Docker is not installed (Category
D blocker, carried forward through Phases 1-4). Execute via
`pytest tests/integration/` once Docker is available.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from src.domain.market_data.entities import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    Instrument,
    OhlcvBar,
)
from src.domain.market_data.repositories import OhlcvBarQuery
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval, Price
from src.infrastructure.persistence.postgres.market_data_models import (
    CorporateActionModel,
    OhlcvBarModel,
)
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.portfolio_models import InstrumentModel
from src.infrastructure.persistence.postgres.repositories.corporate_action_repository import (
    SqlAlchemyCorporateActionRepository,
)
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
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


def _make_instrument(symbol: str = "AAPL") -> Instrument:
    return Instrument(
        id=InstrumentId(uuid.uuid4()),
        symbol=symbol,
        exchange="NASDAQ",
        name="Apple Inc.",
        asset_type=AssetType.EQUITY,
        currency="USD",
        sector="Technology",
        industry="Consumer Electronics",
        ipo_date=None,
        is_active=True,
        created_at=datetime.now(UTC),
    )


class TestSqlAlchemyInstrumentRepository:
    async def test_save_and_get_by_id_round_trips(self, session: AsyncSession) -> None:
        repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument()
        await repo.save(instrument)
        await session.commit()

        fetched = await repo.get_by_id(instrument.id)
        assert fetched is not None
        assert fetched.symbol == "AAPL"
        assert fetched.asset_type == AssetType.EQUITY

    async def test_get_by_symbol_resolves_via_global_unique_index(
        self, session: AsyncSession
    ) -> None:
        repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("MSFT")
        await repo.save(instrument)
        await session.commit()

        fetched = await repo.get_by_symbol("MSFT")
        assert fetched is not None
        assert fetched.id == instrument.id

    async def test_get_by_symbol_returns_none_for_unknown(self, session: AsyncSession) -> None:
        repo = SqlAlchemyInstrumentRepository(session)
        assert await repo.get_by_symbol("NONEXISTENT") is None

    async def test_search_matches_symbol_case_insensitively(self, session: AsyncSession) -> None:
        repo = SqlAlchemyInstrumentRepository(session)
        await repo.save(_make_instrument("GOOGL"))
        await session.commit()

        results = await repo.search("goog")
        assert len(results) == 1
        assert results[0].symbol == "GOOGL"

    async def test_duplicate_symbol_violates_global_unique_index(
        self, session: AsyncSession
    ) -> None:
        # Verifies idx_instruments_symbol_global actually enforces global
        # symbol uniqueness for active instruments (Document 3 §8.1
        # revision) — a real Postgres partial unique index, not something
        # a fake repository could ever catch.
        repo = SqlAlchemyInstrumentRepository(session)
        await repo.save(_make_instrument("DUPTEST"))
        await session.commit()

        duplicate = _make_instrument("DUPTEST")
        session.add(
            InstrumentModel(
                id=duplicate.id.value,
                symbol="DUPTEST",
                exchange="NYSE",
                name="Duplicate Test Co",
                asset_type="equity",
                currency="USD",
                is_active=True,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


class TestSqlAlchemyOhlcvBarRepository:
    async def test_save_and_query_round_trips(self, session: AsyncSession) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("BARTEST1")
        await instrument_repo.save(instrument)
        await session.commit()

        bar_repo = SqlAlchemyOhlcvBarRepository(session)
        bar = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=datetime(2026, 1, 1, tzinfo=UTC),
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            adjusted_close=Price(Decimal("105")),
            volume=1_000_000,
            is_closed=True,
            source="test",
            created_at=datetime.now(UTC),
        )
        await bar_repo.save(bar)
        await session.commit()

        results = await bar_repo.query(
            OhlcvBarQuery(instrument_id=instrument.id, interval=Interval.ONE_DAY)
        )
        assert len(results) == 1
        assert results[0].close.amount == Decimal("105.00000000")

    async def test_save_many_upserts_on_conflict(self, session: AsyncSession) -> None:
        # Verifies the real Postgres INSERT...ON CONFLICT DO UPDATE
        # actually works against the composite primary key
        # (instrument_id, interval, bar_time) — a fake repository's dict
        # keying could never catch a real constraint-name mismatch here.
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("BARTEST2")
        await instrument_repo.save(instrument)
        await session.commit()

        bar_repo = SqlAlchemyOhlcvBarRepository(session)
        bar_time = datetime(2026, 1, 2, tzinfo=UTC)
        original = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=bar_time,
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("100")),
            adjusted_close=Price(Decimal("100")),
            volume=1000,
            is_closed=False,  # still forming
            source="test",
            created_at=datetime.now(UTC),
        )
        await bar_repo.save_many((original,))
        await session.commit()

        updated = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=bar_time,
            open=Price(Decimal("100")),
            high=Price(Decimal("115")),
            low=Price(Decimal("95")),
            close=Price(Decimal("112")),  # bar closed at a different price
            adjusted_close=Price(Decimal("112")),
            volume=5000,
            is_closed=True,  # now closed
            source="test",
            created_at=datetime.now(UTC),
        )
        await bar_repo.save_many((updated,))
        await session.commit()

        results = await bar_repo.query(
            OhlcvBarQuery(instrument_id=instrument.id, interval=Interval.ONE_DAY)
        )
        assert len(results) == 1  # upsert, not a duplicate row
        assert results[0].close.amount == Decimal("112.00000000")
        assert results[0].is_closed is True

    async def test_get_latest_closed_bar_excludes_unclosed(self, session: AsyncSession) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("BARTEST3")
        await instrument_repo.save(instrument)
        await session.commit()

        bar_repo = SqlAlchemyOhlcvBarRepository(session)
        closed_bar = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=datetime(2026, 1, 1, tzinfo=UTC),
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            adjusted_close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="test",
            created_at=datetime.now(UTC),
        )
        unclosed_bar = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=datetime(2026, 1, 2, tzinfo=UTC),
            open=Price(Decimal("105")),
            high=Price(Decimal("108")),
            low=Price(Decimal("104")),
            close=Price(Decimal("107")),
            adjusted_close=Price(Decimal("107")),
            volume=500,
            is_closed=False,
            source="test",
            created_at=datetime.now(UTC),
        )
        await bar_repo.save_many((closed_bar, unclosed_bar))
        await session.commit()

        latest = await bar_repo.get_latest_closed_bar(instrument.id, Interval.ONE_DAY)
        assert latest is not None
        assert latest.bar_time == datetime(2026, 1, 1, tzinfo=UTC)

    async def test_check_constraint_rejects_invalid_interval(self, session: AsyncSession) -> None:
        # Defense-in-depth: even bypassing domain validation via a raw
        # model, the DB CHECK constraint is the last line of defense.
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("BARTEST4")
        await instrument_repo.save(instrument)
        await session.commit()

        bad_model = OhlcvBarModel(
            instrument_id=instrument.id.value,
            interval="not_a_real_interval",
            bar_time=datetime(2026, 1, 1, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            adjusted_close=Decimal("105"),
            volume=1000,
            is_closed=True,
            source="test",
        )
        session.add(bad_model)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_apply_adjustment_factor_before_date(self, session: AsyncSession) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("BARTEST5")
        await instrument_repo.save(instrument)
        await session.commit()

        bar_repo = SqlAlchemyOhlcvBarRepository(session)
        old_bar = OhlcvBar(
            instrument_id=instrument.id,
            interval=Interval.ONE_DAY,
            bar_time=datetime(2025, 12, 1, tzinfo=UTC),
            open=Price(Decimal("200")),
            high=Price(Decimal("210")),
            low=Price(Decimal("195")),
            close=Price(Decimal("200")),
            adjusted_close=Price(Decimal("200")),
            volume=1000,
            is_closed=True,
            source="test",
            created_at=datetime.now(UTC),
        )
        await bar_repo.save_many((old_bar,))
        await session.commit()

        count = await bar_repo.apply_adjustment_factor_before_date(
            instrument.id, date(2026, 1, 1), Decimal("0.5")
        )
        await session.commit()
        assert count == 1

        results = await bar_repo.query(
            OhlcvBarQuery(instrument_id=instrument.id, interval=Interval.ONE_DAY)
        )
        assert results[0].adjusted_close.amount == Decimal("100.00000000")


class TestSqlAlchemyCorporateActionRepository:
    async def test_save_and_list_for_instrument(self, session: AsyncSession) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("CATEST1")
        await instrument_repo.save(instrument)
        await session.commit()

        action_repo = SqlAlchemyCorporateActionRepository(session)
        action = CorporateAction(
            id=CorporateActionId.new(),
            instrument_id=instrument.id,
            action_type=CorporateActionType.SPLIT,
            ratio=Decimal("2"),
            cash_amount=None,
            ex_date=date(2026, 1, 1),
            announced_at=None,
            created_at=datetime.now(UTC),
        )
        await action_repo.save(action)
        await session.commit()

        results = await action_repo.list_for_instrument(instrument.id)
        assert len(results) == 1
        assert results[0].action_type == CorporateActionType.SPLIT

    async def test_exists_check_matches_unique_constraint(self, session: AsyncSession) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("CATEST2")
        await instrument_repo.save(instrument)
        await session.commit()

        action_repo = SqlAlchemyCorporateActionRepository(session)
        action = CorporateAction(
            id=CorporateActionId.new(),
            instrument_id=instrument.id,
            action_type=CorporateActionType.DIVIDEND,
            ratio=None,
            cash_amount=Price(Decimal("1.50")),
            ex_date=date(2026, 2, 1),
            announced_at=None,
            created_at=datetime.now(UTC),
        )
        await action_repo.save(action)
        await session.commit()

        assert await action_repo.exists(instrument.id, "dividend", date(2026, 2, 1)) is True
        assert await action_repo.exists(instrument.id, "split", date(2026, 2, 1)) is False

    async def test_duplicate_action_violates_unique_constraint(self, session: AsyncSession) -> None:
        # Verifies UNIQUE(instrument_id, action_type, ex_date) is a real
        # Postgres constraint, not just an application-layer convention.
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("CATEST3")
        await instrument_repo.save(instrument)
        await session.commit()

        action_repo = SqlAlchemyCorporateActionRepository(session)
        ex_date = date(2026, 3, 1)
        first = CorporateAction(
            id=CorporateActionId.new(),
            instrument_id=instrument.id,
            action_type=CorporateActionType.SPLIT,
            ratio=Decimal("2"),
            cash_amount=None,
            ex_date=ex_date,
            announced_at=None,
            created_at=datetime.now(UTC),
        )
        await action_repo.save(first)
        await session.commit()

        duplicate = CorporateActionModel(
            id=uuid.uuid4(),
            instrument_id=instrument.id.value,
            action_type="split",
            ratio=Decimal("3"),
            cash_amount=None,
            ex_date=ex_date,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_check_constraint_rejects_invalid_action_type(
        self, session: AsyncSession
    ) -> None:
        instrument_repo = SqlAlchemyInstrumentRepository(session)
        instrument = _make_instrument("CATEST4")
        await instrument_repo.save(instrument)
        await session.commit()

        bad_model = CorporateActionModel(
            id=uuid.uuid4(),
            instrument_id=instrument.id.value,
            action_type="not_a_real_type",
            ratio=None,
            cash_amount=None,
            ex_date=date(2026, 4, 1),
        )
        session.add(bad_model)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
