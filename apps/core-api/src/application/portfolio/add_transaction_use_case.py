"""AddTransactionUseCase — the single write path for every transaction type
(buy/sell/dividend/split/transfer_in/transfer_out/deposit/withdrawal).

Per Document 3 §3.4 rule #1: all Holding mutations go through
Portfolio.apply_transaction(); this use case's job is to (1) enforce
ownership, (2) construct the correctly-shaped Transaction for the
requested type, (3) apply it to the loaded aggregate, (4) persist both the
transaction record and the updated portfolio/holdings atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.portfolio.ownership import get_owned_portfolio_or_raise
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
    ) -> None:
        self._portfolio_repository = portfolio_repository
        self._transaction_repository = transaction_repository

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

        return AddTransactionResult(transaction=transaction, realized_gain=realized_gain)
