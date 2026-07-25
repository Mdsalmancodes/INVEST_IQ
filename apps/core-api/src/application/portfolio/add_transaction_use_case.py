"""AddTransactionUseCase — the single write path for every transaction type
(buy/sell/dividend/split/transfer_in/transfer_out/deposit/withdrawal).

Per Document 3 §3.4 rule #1: all Holding mutations go through
Portfolio.apply_transaction(); this use case's job is to (1) enforce
ownership, (2) construct the correctly-shaped Transaction for the
requested type, (3) apply it to the loaded aggregate, (4) persist both the
transaction record and the updated portfolio/holdings atomically.

Phase 8 addition: optionally records an audit entry when a transaction's
total value meets or exceeds a configurable threshold — Document 6 §15.6
explicitly names "large transaction (> configurable threshold)" in its
required audit-logged actions list. Both audit_logger and
large_transaction_threshold_usd default to None/disabled so this Phase 3
use case's existing constructor call sites and tests remain unchanged;
audit logging is purely additive here, never a required dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.auth.audit_logger import AuditLogger
from src.application.portfolio.ownership import get_owned_portfolio_or_raise
from src.domain.auth.value_objects import UserId
from src.domain.portfolio.entities import RealizedGainEvent, Transaction, TransactionType
from src.domain.portfolio.repositories import PortfolioRepository, TransactionRepository
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)


@dataclass(frozen=True, slots=True)
class AddTransactionCommand:
    portfolio_id: PortfolioId
    requesting_user_id: str
    type: TransactionType
    executed_at: datetime
    instrument_id: InstrumentId | None = None
    quantity: Quantity | None = None
    price: Money | None = None
    fees: Money = Money.zero()
    split_ratio: float | None = None
    related_portfolio_id: PortfolioId | None = None
    cash_amount: Money | None = None


@dataclass(frozen=True, slots=True)
class AddTransactionResult:
    transaction: Transaction
    realized_gain: RealizedGainEvent | None


class AddTransactionUseCase:
    def __init__(
        self,
        portfolio_repository: PortfolioRepository,
        transaction_repository: TransactionRepository,
        audit_logger: AuditLogger | None = None,
        large_transaction_threshold_usd: float | None = None,
    ) -> None:
        self._portfolio_repository = portfolio_repository
        self._transaction_repository = transaction_repository
        self._audit_logger = audit_logger
        self._large_transaction_threshold_usd = large_transaction_threshold_usd

    async def execute(self, command: AddTransactionCommand) -> AddTransactionResult:
        portfolio = await get_owned_portfolio_or_raise(
            self._portfolio_repository, command.portfolio_id, command.requesting_user_id
        )

        transaction = Transaction(
            id=TransactionId.new(),
            portfolio_id=portfolio.id,
            instrument_id=command.instrument_id,
            type=command.type,
            quantity=command.quantity,
            price=command.price,
            fees=command.fees,
            split_ratio=command.split_ratio,
            related_portfolio_id=command.related_portfolio_id,
            cash_amount=command.cash_amount,
            executed_at=command.executed_at,
            created_at=datetime.now(command.executed_at.tzinfo),
        )

        # Raises a domain exception (e.g. InsufficientHoldingQuantityError)
        # BEFORE any persistence occurs if the transaction is invalid against
        # current holdings — Transaction/save() below only runs on success.
        realized_gain = portfolio.apply_transaction(transaction)

        await self._transaction_repository.save(transaction)
        await self._portfolio_repository.save(portfolio)

        await self._record_large_transaction_audit_if_applicable(command, transaction)

        return AddTransactionResult(transaction=transaction, realized_gain=realized_gain)

    async def _record_large_transaction_audit_if_applicable(
        self, command: AddTransactionCommand, transaction: Transaction
    ) -> None:
        if self._audit_logger is None or self._large_transaction_threshold_usd is None:
            return
        value = _transaction_value(command)
        if value is None or float(value.amount) < self._large_transaction_threshold_usd:
            return
        await self._audit_logger.record(
            action="portfolio.large_transaction",
            user_id=UserId.from_string(command.requesting_user_id),
            resource_type="transaction",
            resource_id=str(transaction.id),
            metadata={
                "portfolio_id": str(command.portfolio_id),
                "transaction_type": command.type.value,
                "value_usd": str(value.amount),
            },
        )


def _transaction_value(command: AddTransactionCommand) -> Money | None:
    """Best-effort total value for the large-transaction audit threshold —
    price*quantity for buy/sell-style transactions, cash_amount for
    cash-only types (deposit/withdrawal/dividend); returns None for types
    with neither (e.g. a stock split, which has no dollar value of its
    own to threshold against)."""
    if command.price is not None and command.quantity is not None:
        return command.price * command.quantity.value
    if command.cash_amount is not None:
        return command.cash_amount
    return None
