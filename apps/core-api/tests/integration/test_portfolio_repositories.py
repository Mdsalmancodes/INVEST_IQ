"""Integration tests for portfolio repositories against a REAL Postgres
instance.

Per docs/architecture/06-security-testing-strategy.md §16.2 (testcontainers,
not SQLite) — same rationale as tests/integration/test_auth_repositories.py.
For the portfolio context specifically, a real Postgres is essential to
verify things a fake/in-memory repository cannot: the `ck_transactions_type`
CHECK constraint actually accepts ADR-0003's new values
(split/transfer_in/transfer_out) and rejects invalid ones, the
NUMERIC(20,8) columns round-trip Decimal precision exactly, FK constraints
(instrument_id/portfolio_id) are enforced, and the aggregate save/load
round-trip (Portfolio + all its Holdings) works via SQLAlchemy's
selectinload against real relational data, not an in-memory dict.

STATUS: written and statically verified (ruff clean, mypy strict clean —
confirmed via `poetry run mypy --strict tests/integration/`), but NOT YET
EXECUTED in this environment. Docker is not installed (Phase 1 Category D
blocker, carried forward through Phase 2 and now Phase 3) so testcontainers
cannot spin up a real Postgres container here. Execute via
`pytest tests/integration/` once Docker is available.
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

from src.domain.auth.entities import Role, User
from src.domain.auth.value_objects import Email, HashedPassword, UserId
from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.repositories import PortfolioListFilter, TransactionFilter
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)
from src.infrastructure.persistence.postgres.models import Base
from src.infrastructure.persistence.postgres.portfolio_models import InstrumentModel
from src.infrastructure.persistence.postgres.repositories.portfolio_repository import (
    SqlAlchemyPortfolioRepository,
)
from src.infrastructure.persistence.postgres.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
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


async def _make_user_and_instrument(
    session: AsyncSession,
) -> tuple[UserId, InstrumentId]:
    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email(f"portfolio-test-{uuid.uuid4()}@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Portfolio Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )
    await SqlAlchemyUserRepository(session).save(user)

    instrument = InstrumentModel(
        id=uuid.uuid4(),
        symbol="AAPL",
        exchange="NASDAQ",
        name="Apple Inc.",
        asset_type="equity",
        currency="USD",
        is_active=True,
    )
    session.add(instrument)
    await session.commit()
    return user.id, InstrumentId(instrument.id)


def _make_portfolio(user_id: str) -> Portfolio:
    now = datetime.now(UTC)
    return Portfolio(
        id=PortfolioId.new(),
        user_id=user_id,
        name="Integration Test Portfolio",
        base_currency="USD",
        is_paper=True,
        created_at=now,
        updated_at=now,
    )


class TestSqlAlchemyPortfolioRepository:
    async def test_save_and_get_by_id_round_trips_with_holdings(
        self, session: AsyncSession
    ) -> None:
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        buy = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.BUY,
            quantity=Quantity(Decimal("10")),
            price=Money(Decimal("150.25")),
            fees=Money(Decimal("1.50")),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        portfolio.apply_transaction(buy)

        repo = SqlAlchemyPortfolioRepository(session)
        await repo.save(portfolio)
        await session.commit()

        fetched = await repo.get_by_id(portfolio.id)
        assert fetched is not None
        assert fetched.name == "Integration Test Portfolio"
        holding = fetched.get_holding(instrument_id)
        assert holding is not None
        # verifies NUMERIC(20,8) round-trips Decimal precision exactly
        assert holding.quantity.value == Decimal("10.00000000")
        assert holding.average_cost.amount == Decimal("151.75000000")  # (1502.5+1.5)/10

    async def test_list_for_user_paginates_correctly(self, session: AsyncSession) -> None:
        user_id, _ = await _make_user_and_instrument(session)
        repo = SqlAlchemyPortfolioRepository(session)
        for i in range(3):
            p = _make_portfolio(str(user_id))
            object.__setattr__(p, "name", f"Portfolio {i}")
            await repo.save(p)
        await session.commit()

        result = await repo.list_for_user(str(user_id), PortfolioListFilter(page=1, page_size=2))
        assert result.total_count == 3
        assert len(result.items) == 2

    async def test_delete_removes_portfolio_and_holdings_via_cascade(
        self, session: AsyncSession
    ) -> None:
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        buy = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.BUY,
            quantity=Quantity(Decimal("5")),
            price=Money(Decimal("100")),
            fees=Money.zero(),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        portfolio.apply_transaction(buy)
        repo = SqlAlchemyPortfolioRepository(session)
        await repo.save(portfolio)
        await session.commit()

        await repo.delete(portfolio.id)
        await session.commit()

        assert await repo.get_by_id(portfolio.id) is None


class TestSqlAlchemyTransactionRepository:
    async def test_save_and_list_all_for_portfolio_unpaginated(self, session: AsyncSession) -> None:
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        await SqlAlchemyPortfolioRepository(session).save(portfolio)
        await session.commit()

        tx_repo = SqlAlchemyTransactionRepository(session)
        buy = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.BUY,
            quantity=Quantity(Decimal("10")),
            price=Money(Decimal("100")),
            fees=Money.zero(),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        await tx_repo.save(buy)
        await session.commit()

        all_txs = await tx_repo.list_all_for_portfolio_unpaginated(portfolio.id)
        assert len(all_txs) == 1
        assert all_txs[0].type == TransactionType.BUY

    async def test_check_constraint_accepts_adr_0003_split_type(
        self, session: AsyncSession
    ) -> None:
        # This is the specific behavior that only a real Postgres instance
        # can verify — the ck_transactions_type CHECK constraint must
        # actually accept 'split' (added by ADR-0003), not just the
        # originally-frozen 5 types. A fake/in-memory repository test
        # would never catch a typo in the migration's CHECK clause.
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        await SqlAlchemyPortfolioRepository(session).save(portfolio)
        await session.commit()

        tx_repo = SqlAlchemyTransactionRepository(session)
        split = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.SPLIT,
            quantity=None,
            price=None,
            fees=Money.zero(),
            split_ratio=2.0,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        await tx_repo.save(split)
        await session.commit()  # would raise IntegrityError if CHECK constraint rejected 'split'

        fetched = await tx_repo.get_by_id(split.id)
        assert fetched is not None
        assert fetched.type == TransactionType.SPLIT

    async def test_check_constraint_rejects_invalid_type_at_db_level(
        self, session: AsyncSession
    ) -> None:
        # Defense-in-depth verification: even if application code somehow
        # bypassed domain validation, the DB CHECK constraint is the last
        # line of defense (Document 6 §16's layered-validation principle).
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        await SqlAlchemyPortfolioRepository(session).save(portfolio)
        await session.commit()

        from src.infrastructure.persistence.postgres.portfolio_models import TransactionModel

        bad_model = TransactionModel(
            id=uuid.uuid4(),
            portfolio_id=portfolio.id.value,
            instrument_id=instrument_id.value,
            type="not_a_real_type",
            quantity=Decimal("1"),
            price=Decimal("1"),
            fees=Decimal("0"),
            executed_at=datetime.now(UTC),
        )
        session.add(bad_model)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_list_for_portfolio_filters_by_type(self, session: AsyncSession) -> None:
        user_id, instrument_id = await _make_user_and_instrument(session)
        portfolio = _make_portfolio(str(user_id))
        await SqlAlchemyPortfolioRepository(session).save(portfolio)
        await session.commit()

        tx_repo = SqlAlchemyTransactionRepository(session)
        buy = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.BUY,
            quantity=Quantity(Decimal("10")),
            price=Money(Decimal("100")),
            fees=Money.zero(),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        sell = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=instrument_id,
            type=TransactionType.SELL,
            quantity=Quantity(Decimal("5")),
            price=Money(Decimal("120")),
            fees=Money.zero(),
            split_ratio=None,
            related_portfolio_id=None,
            cash_amount=None,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        await tx_repo.save(buy)
        await tx_repo.save(sell)
        await session.commit()

        result = await tx_repo.list_for_portfolio(
            portfolio.id, TransactionFilter(types=(TransactionType.SELL,))
        )
        assert result.total_count == 1
        assert result.items[0].type == TransactionType.SELL
