"""Unit tests for the Phase 3 application-layer use cases — CreatePortfolio,
GetPortfolio, ListPortfolios, UpdatePortfolio, DeletePortfolio,
AddTransaction, ListTransactions, GetHoldings, GetPortfolioSummary."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.application.portfolio.add_transaction_use_case import (
    AddTransactionCommand,
    AddTransactionUseCase,
)
from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.application.portfolio.create_portfolio_use_case import (
    CreatePortfolioCommand,
    CreatePortfolioUseCase,
)
from src.application.portfolio.get_holdings_use_case import GetHoldingsUseCase
from src.application.portfolio.get_portfolio_summary_use_case import GetPortfolioSummaryUseCase
from src.application.portfolio.get_portfolio_use_case import (
    GetPortfolioUseCase,
    ListPortfoliosQuery,
    ListPortfoliosUseCase,
)
from src.application.portfolio.list_transactions_use_case import (
    ListTransactionsQuery,
    ListTransactionsUseCase,
)
from src.application.portfolio.update_portfolio_use_case import (
    DeletePortfolioUseCase,
    UpdatePortfolioCommand,
    UpdatePortfolioUseCase,
)
from src.domain.portfolio.entities import Portfolio, Transaction, TransactionType
from src.domain.portfolio.exceptions import (
    InsufficientHoldingQuantityError,
    PortfolioNotFoundError,
    PortfolioOwnershipError,
)
from src.domain.portfolio.repositories import (
    PageResult,
    PortfolioListFilter,
    PortfolioPageResult,
    TransactionFilter,
)
from src.domain.portfolio.value_objects import InstrumentId, Money, PortfolioId, Quantity

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_A = InstrumentId(uuid.uuid4())


class FakePortfolioRepository:
    def __init__(self) -> None:
        self._store: dict[str, Portfolio] = {}

    async def save(self, portfolio: Portfolio) -> None:
        self._store[str(portfolio.id)] = portfolio

    async def get_by_id(self, portfolio_id: PortfolioId) -> Portfolio | None:
        return self._store.get(str(portfolio_id))

    async def list_for_user(
        self, user_id: str, filters: PortfolioListFilter
    ) -> PortfolioPageResult:
        matching = [p for p in self._store.values() if p.user_id == user_id]
        if filters.is_paper is not None:
            matching = [p for p in matching if p.is_paper == filters.is_paper]
        return PortfolioPageResult(
            items=tuple(matching), total_count=len(matching), page=1, page_size=20
        )

    async def delete(self, portfolio_id: PortfolioId) -> None:
        self._store.pop(str(portfolio_id), None)

    async def exists_with_name_for_user(self, user_id: str, name: str) -> bool:
        return any(p.user_id == user_id and p.name == name for p in self._store.values())


class FakeTransactionRepository:
    def __init__(self) -> None:
        self._store: list[Transaction] = []

    async def save(self, transaction: Transaction) -> None:
        self._store.append(transaction)

    async def get_by_id(self, transaction_id: object) -> Transaction | None:
        return None

    async def list_for_portfolio(
        self, portfolio_id: PortfolioId, filters: TransactionFilter
    ) -> PageResult:
        matching = [tx for tx in self._store if tx.portfolio_id == portfolio_id]
        return PageResult(items=tuple(matching), total_count=len(matching), page=1, page_size=20)

    async def list_all_for_portfolio_unpaginated(
        self, portfolio_id: PortfolioId
    ) -> tuple[Transaction, ...]:
        return tuple(tx for tx in self._store if tx.portfolio_id == portfolio_id)


class FakePriceProvider:
    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        return Money(Decimal("100"))

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        return Money(Decimal("95"))


@pytest.mark.asyncio
class TestCreatePortfolioUseCase:
    async def test_creates_and_persists(self) -> None:
        repo = FakePortfolioRepository()
        use_case = CreatePortfolioUseCase(repo)
        portfolio = await use_case.execute(
            CreatePortfolioCommand(user_id="user-1", name="Retirement")
        )
        assert portfolio.name == "Retirement"
        assert portfolio.user_id == "user-1"
        assert portfolio.is_paper is True  # default
        stored = await repo.get_by_id(portfolio.id)
        assert stored is not None


@pytest.mark.asyncio
class TestGetPortfolioUseCase:
    async def test_returns_owned_portfolio(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Retirement")
        )
        result = await GetPortfolioUseCase(repo).execute(created.id, "user-1")
        assert result.id == created.id

    async def test_raises_not_found_for_unknown_id(self) -> None:
        repo = FakePortfolioRepository()
        with pytest.raises(PortfolioNotFoundError):
            await GetPortfolioUseCase(repo).execute(PortfolioId.new(), "user-1")

    async def test_raises_ownership_error_for_wrong_user(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Retirement")
        )
        with pytest.raises(PortfolioOwnershipError):
            await GetPortfolioUseCase(repo).execute(created.id, "user-2")


@pytest.mark.asyncio
class TestListPortfoliosUseCase:
    async def test_lists_only_requesting_users_portfolios(self) -> None:
        repo = FakePortfolioRepository()
        await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="A")
        )
        await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-2", name="B")
        )
        result = await ListPortfoliosUseCase(repo).execute(ListPortfoliosQuery(user_id="user-1"))
        assert result.total_count == 1
        assert result.items[0].name == "A"

    async def test_filters_by_is_paper(self) -> None:
        repo = FakePortfolioRepository()
        await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Paper", is_paper=True)
        )
        await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Real", is_paper=False)
        )
        result = await ListPortfoliosUseCase(repo).execute(
            ListPortfoliosQuery(user_id="user-1", is_paper=False)
        )
        assert result.total_count == 1
        assert result.items[0].name == "Real"


@pytest.mark.asyncio
class TestUpdatePortfolioUseCase:
    async def test_updates_name(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Old Name")
        )
        updated = await UpdatePortfolioUseCase(repo).execute(
            UpdatePortfolioCommand(
                portfolio_id=created.id, requesting_user_id="user-1", name="New Name"
            )
        )
        assert updated.name == "New Name"

    async def test_wrong_owner_cannot_update(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="Old Name")
        )
        with pytest.raises(PortfolioOwnershipError):
            await UpdatePortfolioUseCase(repo).execute(
                UpdatePortfolioCommand(
                    portfolio_id=created.id, requesting_user_id="user-2", name="Hacked"
                )
            )


@pytest.mark.asyncio
class TestDeletePortfolioUseCase:
    async def test_deletes_owned_portfolio(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="ToDelete")
        )
        await DeletePortfolioUseCase(repo).execute(created.id, "user-1")
        assert await repo.get_by_id(created.id) is None

    async def test_wrong_owner_cannot_delete(self) -> None:
        repo = FakePortfolioRepository()
        created = await CreatePortfolioUseCase(repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="ToDelete")
        )
        with pytest.raises(PortfolioOwnershipError):
            await DeletePortfolioUseCase(repo).execute(created.id, "user-2")
        assert await repo.get_by_id(created.id) is not None  # untouched


@pytest.mark.asyncio
class TestAddTransactionUseCase:
    async def test_buy_creates_holding(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        result = await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),
            )
        )
        assert result.realized_gain is None
        stored_portfolio = await portfolio_repo.get_by_id(created.id)
        assert stored_portfolio is not None
        holding = stored_portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("10.00000000")

    async def test_sell_returns_realized_gain(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),
            )
        )
        result = await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.SELL,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("5")),
                price=Money(Decimal("150")),
            )
        )
        assert result.realized_gain is not None
        assert result.realized_gain.gain.amount == Decimal("250.00000000")

    async def test_wrong_owner_cannot_add_transaction(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        with pytest.raises(PortfolioOwnershipError):
            await use_case.execute(
                AddTransactionCommand(
                    portfolio_id=created.id,
                    requesting_user_id="user-2",
                    type=TransactionType.BUY,
                    executed_at=NOW,
                    instrument_id=INSTRUMENT_A,
                    quantity=Quantity(Decimal("10")),
                    price=Money(Decimal("100")),
                )
            )

    async def test_records_a_large_transaction_audit_entry_when_over_threshold(self) -> None:
        from src.application.auth.audit_logger import AuditLogger
        from src.domain.auth.value_objects import UserId
        from tests.unit.application.fakes import FakeAuditLogRepository

        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        audit_repo = FakeAuditLogRepository()
        owner_user_id = str(UserId.new())
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id=owner_user_id, name="P")
        )
        use_case = AddTransactionUseCase(
            portfolio_repo,
            tx_repo,
            audit_logger=AuditLogger(audit_repo),
            large_transaction_threshold_usd=10_000.0,
        )

        await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id=owner_user_id,
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("200")),
                price=Money(Decimal("100")),  # 200 * 100 = 20,000 >= 10,000 threshold
            )
        )

        assert len(audit_repo.entries) == 1
        assert audit_repo.entries[0].action == "portfolio.large_transaction"

    async def test_does_not_record_an_audit_entry_when_under_threshold(self) -> None:
        from src.application.auth.audit_logger import AuditLogger
        from src.domain.auth.value_objects import UserId
        from tests.unit.application.fakes import FakeAuditLogRepository

        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        audit_repo = FakeAuditLogRepository()
        owner_user_id = str(UserId.new())
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id=owner_user_id, name="P")
        )
        use_case = AddTransactionUseCase(
            portfolio_repo,
            tx_repo,
            audit_logger=AuditLogger(audit_repo),
            large_transaction_threshold_usd=10_000.0,
        )

        await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id=owner_user_id,
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),  # 10 * 100 = 1,000 < 10,000 threshold
            )
        )

        assert audit_repo.entries == []

    async def test_works_without_an_audit_logger_or_threshold_injected(self) -> None:
        # Backward-compatible constructor defaults (audit_logger=None,
        # large_transaction_threshold_usd=None) — every pre-Phase-8 call
        # site/test (like the ones above in this same class) continues
        # to work unchanged.
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)

        await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("200")),
                price=Money(Decimal("100")),
            )
        )  # should not raise

    async def test_invalid_sell_does_not_persist_anything(self) -> None:
        # Selling more than held must raise BEFORE any save() call —
        # verifies the "no partial persistence on domain-rule violation"
        # guarantee documented in AddTransactionUseCase's docstring.
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        with pytest.raises(InsufficientHoldingQuantityError):
            await use_case.execute(
                AddTransactionCommand(
                    portfolio_id=created.id,
                    requesting_user_id="user-1",
                    type=TransactionType.SELL,
                    executed_at=NOW,
                    instrument_id=INSTRUMENT_A,
                    quantity=Quantity(Decimal("10")),
                    price=Money(Decimal("100")),
                )
            )
        assert len(tx_repo._store) == 0

    async def test_deposit_transaction(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        result = await use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.DEPOSIT,
                executed_at=NOW,
                cash_amount=Money(Decimal("1000")),
            )
        )
        assert result.transaction.cash_amount is not None
        assert result.transaction.cash_amount.amount == Decimal("1000.00000000")


@pytest.mark.asyncio
class TestListTransactionsUseCase:
    async def test_lists_transactions_for_owned_portfolio(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        add_use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        await add_use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),
            )
        )
        list_use_case = ListTransactionsUseCase(portfolio_repo, tx_repo)
        result = await list_use_case.execute(
            ListTransactionsQuery(portfolio_id=created.id, requesting_user_id="user-1")
        )
        assert result.total_count == 1

    async def test_wrong_owner_cannot_list(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        list_use_case = ListTransactionsUseCase(portfolio_repo, tx_repo)
        with pytest.raises(PortfolioOwnershipError):
            await list_use_case.execute(
                ListTransactionsQuery(portfolio_id=created.id, requesting_user_id="user-2")
            )


@pytest.mark.asyncio
class TestGetHoldingsUseCase:
    async def test_excludes_zero_quantity_holdings(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        add_use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        await add_use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),
            )
        )
        await add_use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.SELL,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("150")),
            )
        )
        holdings = await GetHoldingsUseCase(portfolio_repo).execute(created.id, "user-1")
        assert len(holdings) == 0


@pytest.mark.asyncio
class TestGetPortfolioSummaryUseCase:
    async def test_returns_summary_for_owned_portfolio(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        add_use_case = AddTransactionUseCase(portfolio_repo, tx_repo)
        await add_use_case.execute(
            AddTransactionCommand(
                portfolio_id=created.id,
                requesting_user_id="user-1",
                type=TransactionType.BUY,
                executed_at=NOW,
                instrument_id=INSTRUMENT_A,
                quantity=Quantity(Decimal("10")),
                price=Money(Decimal("100")),
            )
        )
        calc_service = PortfolioCalculationService(FakePriceProvider(), tx_repo)
        summary_use_case = GetPortfolioSummaryUseCase(portfolio_repo, calc_service)
        summary = await summary_use_case.execute(created.id, "user-1")
        assert summary.total_investment.amount == Decimal("1000.00000000")
        assert summary.current_value.amount == Decimal("1000.00000000")

    async def test_wrong_owner_cannot_get_summary(self) -> None:
        portfolio_repo = FakePortfolioRepository()
        tx_repo = FakeTransactionRepository()
        created = await CreatePortfolioUseCase(portfolio_repo).execute(
            CreatePortfolioCommand(user_id="user-1", name="P")
        )
        calc_service = PortfolioCalculationService(FakePriceProvider(), tx_repo)
        summary_use_case = GetPortfolioSummaryUseCase(portfolio_repo, calc_service)
        with pytest.raises(PortfolioOwnershipError):
            await summary_use_case.execute(created.id, "user-2")
