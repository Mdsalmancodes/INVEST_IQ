"""Domain entities for the portfolio bounded context.

Per Document 3 §3.4 (Portfolio aggregate rules) and ADR-0003 (split/transfer
transaction types). The Portfolio aggregate root owns Holdings — per
Document 3 §3.4 rule #1, no code outside this module mutates a Holding
directly; all mutations go through Portfolio.apply_transaction() to
guarantee cost-basis and quantity invariants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.portfolio.exceptions import (
    InsufficientHoldingQuantityError,
    InvalidTransactionError,
)
from src.domain.portfolio.value_objects import (
    HoldingId,
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)


class TransactionType(str, Enum):
    """Per ADR-0003: extends the frozen architecture's 5 types with `split`,
    `transfer_in`, `transfer_out`."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SPLIT = "split"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


# Transaction types that require an instrument_id (position-affecting) —
# deposit/withdrawal are pure cash movements with no instrument.
_INSTRUMENT_REQUIRED_TYPES = frozenset(
    {
        TransactionType.BUY,
        TransactionType.SELL,
        TransactionType.DIVIDEND,
        TransactionType.SPLIT,
        TransactionType.TRANSFER_IN,
        TransactionType.TRANSFER_OUT,
    }
)


@dataclass(slots=True)
class Transaction:
    """An immutable historical record (Document 3 DDD §3.4's "append-only"
    pattern, same principle already applied to PredictionRun in Document 4
    §10.1) of a single event that occurred against a Portfolio. Once
    persisted, a Transaction is never mutated — corrections are made by
    recording an offsetting transaction, never by editing history.
    """

    id: TransactionId
    portfolio_id: PortfolioId
    instrument_id: InstrumentId | None
    type: TransactionType
    quantity: Quantity | None  # None for deposit/withdrawal
    price: Money | None  # None for deposit/withdrawal; per-share price for buy/sell/dividend
    fees: Money
    split_ratio: float | None  # ADR-0003 — only for TransactionType.SPLIT
    related_portfolio_id: PortfolioId | None  # ADR-0003 — only for internal transfers
    cash_amount: Money | None  # for deposit/withdrawal: the cash amount moved
    executed_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        requires_instrument = self.type in _INSTRUMENT_REQUIRED_TYPES
        if requires_instrument and self.instrument_id is None:
            raise InvalidTransactionError(
                f"Transaction type {self.type.value!r} requires an instrument_id"
            )
        if not requires_instrument and self.instrument_id is not None:
            raise InvalidTransactionError(
                f"Transaction type {self.type.value!r} must not have an instrument_id"
            )

        if self.type == TransactionType.SPLIT:
            if self.split_ratio is None or self.split_ratio <= 0:
                raise InvalidTransactionError("A split transaction requires a positive split_ratio")
            if self.quantity is not None or self.price is not None:
                raise InvalidTransactionError(
                    "A split transaction must not carry quantity or price "
                    "(the ratio alone determines the adjustment)"
                )
        elif self.split_ratio is not None:
            raise InvalidTransactionError(
                f"split_ratio must be None for transaction type {self.type.value!r}"
            )

        if self.type in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL):
            if self.cash_amount is None:
                raise InvalidTransactionError(
                    f"Transaction type {self.type.value!r} requires a cash_amount"
                )
        elif self.cash_amount is not None:
            raise InvalidTransactionError(
                f"cash_amount must be None for transaction type {self.type.value!r}"
            )

        if self.type in (TransactionType.BUY, TransactionType.SELL) and (
            self.quantity is None or self.price is None
        ):
            raise InvalidTransactionError(
                f"Transaction type {self.type.value!r} requires both quantity and price"
            )

        if self.type == TransactionType.DIVIDEND and (self.quantity is None or self.price is None):
            # `price` is the PER-SHARE dividend amount, `quantity` is the
            # number of shares that received it — dividend income is their
            # product, not `price` alone (a lump cash amount would need to
            # be represented as quantity=1, price=<total amount>, which
            # remains valid under this same product-based rule).
            raise InvalidTransactionError(
                "A dividend transaction requires both quantity (shares held) "
                "and price (per-share dividend amount)"
            )


@dataclass(slots=True)
class Holding:
    """A position within a Portfolio — Document 3's Ubiquitous Language:
    "symbol + quantity + cost basis." Mutated ONLY via Portfolio.
    apply_transaction() (Document 3 §3.4 rule #1) — this class's own methods
    are intentionally package-private in spirit (called by Portfolio, not
    by application-layer use cases directly).
    """

    id: HoldingId
    portfolio_id: PortfolioId
    instrument_id: InstrumentId
    quantity: Quantity
    average_cost: Money  # per-share average cost basis
    created_at: datetime
    updated_at: datetime

    def market_value(self, current_price: Money) -> Money:
        return current_price * self.quantity.value

    def total_cost_basis(self) -> Money:
        return self.average_cost * self.quantity.value

    def unrealized_gain(self, current_price: Money) -> Money:
        return self.market_value(current_price) - self.total_cost_basis()

    def _apply_buy(self, quantity: Quantity, price: Money, fees: Money) -> None:
        """Weighted-average cost basis update. Fees are added to the cost
        basis (increases average cost), matching standard brokerage
        cost-basis accounting — fees are not a separately tracked expense
        here, they inflate what was actually paid per share.
        """
        existing_total_cost = self.total_cost_basis()
        new_purchase_cost = (price * quantity.value) + fees
        new_quantity = self.quantity + quantity
        new_total_cost = existing_total_cost + new_purchase_cost
        self.quantity = new_quantity
        self.average_cost = (
            Money(new_total_cost.amount / new_quantity.value)
            if not new_quantity.is_zero()
            else Money.zero()
        )
        self.updated_at = datetime.now(self.updated_at.tzinfo)

    def _apply_sell(self, quantity: Quantity) -> Money:
        """Reduces quantity; average_cost is UNCHANGED by a sell (Document 3
        §3.4's average-cost-basis model — selling some shares doesn't change
        the average cost of the ones remaining). Returns the realized gain
        for the sold portion, computed by the caller using the price at
        which the sale occurred (this method only knows the cost side).
        """
        if quantity.value > self.quantity.value:
            raise InsufficientHoldingQuantityError(
                f"Cannot sell {quantity.value} shares; holding only has {self.quantity.value}"
            )
        cost_of_sold_shares = self.average_cost * quantity.value
        self.quantity = self.quantity - quantity
        self.updated_at = datetime.now(self.updated_at.tzinfo)
        return cost_of_sold_shares

    def _apply_split(self, ratio: float) -> None:
        """A split changes quantity and average_cost inversely, leaving
        total cost basis (and therefore net position value) unchanged —
        ADR-0003's core semantic requirement."""
        from decimal import Decimal

        ratio_decimal = Decimal(str(ratio))
        self.quantity = self.quantity * ratio_decimal
        self.average_cost = Money(self.average_cost.amount / ratio_decimal)
        self.updated_at = datetime.now(self.updated_at.tzinfo)

    def _apply_transfer_in(self, quantity: Quantity, price: Money) -> None:
        """Transfer-in establishes cost basis at the transferred-in price
        (ADR-0003) — treated like a buy for cost-basis purposes but the
        caller (Portfolio.apply_transaction) does NOT count this toward
        Total Investment (no actual cash outflow occurred)."""
        self._apply_buy(quantity, price, fees=Money.zero())

    def _apply_transfer_out(self, quantity: Quantity) -> None:
        """Transfer-out reduces quantity without generating a realized
        gain/loss (ADR-0003) — unlike a sell, no gain is computed here; the
        caller does not add a realized-gain entry for this transaction type."""
        if quantity.value > self.quantity.value:
            raise InsufficientHoldingQuantityError(
                f"Cannot transfer out {quantity.value} shares; "
                f"holding only has {self.quantity.value}"
            )
        self.quantity = self.quantity - quantity
        self.updated_at = datetime.now(self.updated_at.tzinfo)


@dataclass(slots=True)
class RealizedGainEvent:
    """Not persisted as its own table — computed and returned by
    Portfolio.apply_transaction() so the application layer can record it
    (e.g. into an audit trail or a future realized-gains report) without
    the Portfolio aggregate needing to know about persistence."""

    instrument_id: InstrumentId
    quantity: Quantity
    proceeds: Money
    cost_basis: Money

    @property
    def gain(self) -> Money:
        return self.proceeds - self.cost_basis


@dataclass(slots=True)
class Portfolio:
    """Aggregate root — Document 3 §3.4: "Portfolio aggregate owns Holdings.
    No code outside the Portfolio module mutates a Holding directly — all
    mutations go through Portfolio.applyTransaction() to guarantee cost-
    basis and quantity invariants."
    """

    id: PortfolioId
    user_id: str  # kept as a bare str here deliberately — this context
    # doesn't need the full auth.UserId value object's validation, only an
    # opaque ownership key; avoids a cross-bounded-context import
    # (Document 3 DDD §3.2's context map: no direct cross-context coupling
    # beyond the shared UserId concept, referenced by value not by import).
    name: str
    base_currency: str
    is_paper: bool
    created_at: datetime
    updated_at: datetime
    holdings: dict[str, Holding] = field(default_factory=dict)  # keyed by str(instrument_id)

    def get_holding(self, instrument_id: InstrumentId) -> Holding | None:
        return self.holdings.get(str(instrument_id))

    def apply_transaction(self, transaction: Transaction) -> RealizedGainEvent | None:
        """The single entry point for every position-affecting mutation —
        Document 3 §3.4 rule #1. Returns a RealizedGainEvent for `sell`
        transactions (None otherwise), which the application layer may
        persist/report on without this aggregate depending on persistence.
        """
        if transaction.type == TransactionType.BUY:
            self._apply_buy_transaction(transaction)
            return None
        if transaction.type == TransactionType.SELL:
            return self._apply_sell_transaction(transaction)
        if transaction.type == TransactionType.SPLIT:
            self._apply_split_transaction(transaction)
            return None
        if transaction.type == TransactionType.TRANSFER_IN:
            self._apply_transfer_in_transaction(transaction)
            return None
        if transaction.type == TransactionType.TRANSFER_OUT:
            self._apply_transfer_out_transaction(transaction)
            return None
        if transaction.type == TransactionType.DIVIDEND:
            # Dividends do not mutate the Holding's quantity/cost-basis at
            # all (Document 4 §10.5's calculation service treats dividend
            # income as a separate line item, not a position change) — this
            # is intentionally a no-op on the Holding; the transaction
            # record itself is what the dividend-income calculation reads.
            return None
        if transaction.type in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL):
            # Pure cash movements — no Holding involved at all.
            return None
        raise InvalidTransactionError(f"Unhandled transaction type: {transaction.type!r}")

    def _get_or_create_holding(self, instrument_id: InstrumentId) -> Holding:
        existing = self.get_holding(instrument_id)
        if existing is not None:
            return existing
        now = self.updated_at
        new_holding = Holding(
            id=HoldingId.new(),
            portfolio_id=self.id,
            instrument_id=instrument_id,
            quantity=Quantity.zero(),
            average_cost=Money.zero(),
            created_at=now,
            updated_at=now,
        )
        self.holdings[str(instrument_id)] = new_holding
        return new_holding

    def _apply_buy_transaction(self, transaction: Transaction) -> None:
        assert transaction.instrument_id is not None
        assert transaction.quantity is not None
        assert transaction.price is not None
        holding = self._get_or_create_holding(transaction.instrument_id)
        holding._apply_buy(transaction.quantity, transaction.price, transaction.fees)

    def _apply_sell_transaction(self, transaction: Transaction) -> RealizedGainEvent:
        assert transaction.instrument_id is not None
        assert transaction.quantity is not None
        assert transaction.price is not None
        holding = self.get_holding(transaction.instrument_id)
        if holding is None:
            raise InsufficientHoldingQuantityError(
                f"Cannot sell — no holding exists for instrument {transaction.instrument_id}"
            )
        cost_basis = holding._apply_sell(transaction.quantity)
        proceeds = (transaction.price * transaction.quantity.value) - transaction.fees
        return RealizedGainEvent(
            instrument_id=transaction.instrument_id,
            quantity=transaction.quantity,
            proceeds=proceeds,
            cost_basis=cost_basis,
        )

    def _apply_split_transaction(self, transaction: Transaction) -> None:
        assert transaction.instrument_id is not None
        assert transaction.split_ratio is not None
        holding = self.get_holding(transaction.instrument_id)
        if holding is None:
            raise InvalidTransactionError(
                f"Cannot apply split — no holding exists for instrument "
                f"{transaction.instrument_id}"
            )
        holding._apply_split(transaction.split_ratio)

    def _apply_transfer_in_transaction(self, transaction: Transaction) -> None:
        assert transaction.instrument_id is not None
        assert transaction.quantity is not None
        assert transaction.price is not None
        holding = self._get_or_create_holding(transaction.instrument_id)
        holding._apply_transfer_in(transaction.quantity, transaction.price)

    def _apply_transfer_out_transaction(self, transaction: Transaction) -> None:
        assert transaction.instrument_id is not None
        assert transaction.quantity is not None
        holding = self.get_holding(transaction.instrument_id)
        if holding is None:
            raise InsufficientHoldingQuantityError(
                f"Cannot transfer out — no holding exists for instrument "
                f"{transaction.instrument_id}"
            )
        holding._apply_transfer_out(transaction.quantity)
