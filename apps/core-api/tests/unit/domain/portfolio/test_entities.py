"""Unit tests for Portfolio/Holding/Transaction entities — apply_transaction
is the highest-risk business logic in Phase 3 (Document 3 §3.4 rule #1),
so every transaction type and edge case is tested here."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.portfolio.entities import (
    Portfolio,
    Transaction,
    TransactionType,
)
from src.domain.portfolio.exceptions import (
    InsufficientHoldingQuantityError,
    InvalidTransactionError,
)
from src.domain.portfolio.value_objects import (
    InstrumentId,
    Money,
    PortfolioId,
    Quantity,
    TransactionId,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_A = InstrumentId(uuid.uuid4())
INSTRUMENT_B = InstrumentId(uuid.uuid4())


def make_portfolio() -> Portfolio:
    return Portfolio(
        id=PortfolioId.new(),
        user_id="user-1",
        name="My Portfolio",
        base_currency="USD",
        is_paper=False,
        created_at=NOW,
        updated_at=NOW,
    )


def make_buy(
    portfolio_id: PortfolioId,
    instrument_id: InstrumentId,
    quantity: str,
    price: str,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.BUY,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money(Decimal(fees)),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_sell(
    portfolio_id: PortfolioId,
    instrument_id: InstrumentId,
    quantity: str,
    price: str,
    fees: str = "0",
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.SELL,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money(Decimal(fees)),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_split(portfolio_id: PortfolioId, instrument_id: InstrumentId, ratio: float) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.SPLIT,
        quantity=None,
        price=None,
        fees=Money.zero(),
        split_ratio=ratio,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_transfer_in(
    portfolio_id: PortfolioId, instrument_id: InstrumentId, quantity: str, price: str
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.TRANSFER_IN,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(price)),
        fees=Money.zero(),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_transfer_out(
    portfolio_id: PortfolioId, instrument_id: InstrumentId, quantity: str
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.TRANSFER_OUT,
        quantity=Quantity(Decimal(quantity)),
        price=Money.zero(),
        fees=Money.zero(),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_dividend(
    portfolio_id: PortfolioId,
    instrument_id: InstrumentId,
    per_share_amount: str,
    quantity: str = "10",
) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        type=TransactionType.DIVIDEND,
        quantity=Quantity(Decimal(quantity)),
        price=Money(Decimal(per_share_amount)),
        fees=Money.zero(),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=None,
        executed_at=NOW,
        created_at=NOW,
    )


def make_deposit(portfolio_id: PortfolioId, amount: str) -> Transaction:
    return Transaction(
        id=TransactionId.new(),
        portfolio_id=portfolio_id,
        instrument_id=None,
        type=TransactionType.DEPOSIT,
        quantity=None,
        price=None,
        fees=Money.zero(),
        split_ratio=None,
        related_portfolio_id=None,
        cash_amount=Money(Decimal(amount)),
        executed_at=NOW,
        created_at=NOW,
    )


class TestTransactionValidation:
    def test_buy_requires_quantity_and_price(self) -> None:
        with pytest.raises(InvalidTransactionError):
            Transaction(
                id=TransactionId.new(),
                portfolio_id=PortfolioId.new(),
                instrument_id=INSTRUMENT_A,
                type=TransactionType.BUY,
                quantity=None,
                price=Money(Decimal("10")),
                fees=Money.zero(),
                split_ratio=None,
                related_portfolio_id=None,
                cash_amount=None,
                executed_at=NOW,
                created_at=NOW,
            )

    def test_deposit_requires_cash_amount_not_instrument(self) -> None:
        with pytest.raises(InvalidTransactionError):
            Transaction(
                id=TransactionId.new(),
                portfolio_id=PortfolioId.new(),
                instrument_id=INSTRUMENT_A,  # invalid: deposit must not have instrument
                type=TransactionType.DEPOSIT,
                quantity=None,
                price=None,
                fees=Money.zero(),
                split_ratio=None,
                related_portfolio_id=None,
                cash_amount=Money(Decimal("100")),
                executed_at=NOW,
                created_at=NOW,
            )

    def test_deposit_without_cash_amount_raises(self) -> None:
        with pytest.raises(InvalidTransactionError):
            Transaction(
                id=TransactionId.new(),
                portfolio_id=PortfolioId.new(),
                instrument_id=None,
                type=TransactionType.DEPOSIT,
                quantity=None,
                price=None,
                fees=Money.zero(),
                split_ratio=None,
                related_portfolio_id=None,
                cash_amount=None,
                executed_at=NOW,
                created_at=NOW,
            )

    def test_split_requires_positive_ratio(self) -> None:
        with pytest.raises(InvalidTransactionError):
            make_split(PortfolioId.new(), INSTRUMENT_A, ratio=0)

    def test_split_ratio_must_be_none_for_buy(self) -> None:
        with pytest.raises(InvalidTransactionError):
            Transaction(
                id=TransactionId.new(),
                portfolio_id=PortfolioId.new(),
                instrument_id=INSTRUMENT_A,
                type=TransactionType.BUY,
                quantity=Quantity(Decimal("1")),
                price=Money(Decimal("10")),
                fees=Money.zero(),
                split_ratio=2.0,  # invalid for buy
                related_portfolio_id=None,
                cash_amount=None,
                executed_at=NOW,
                created_at=NOW,
            )


class TestApplyBuyTransaction:
    def test_first_buy_creates_holding(self) -> None:
        portfolio = make_portfolio()
        tx = make_buy(portfolio.id, INSTRUMENT_A, "10", "100")
        result = portfolio.apply_transaction(tx)

        assert result is None
        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("10.00000000")
        assert holding.average_cost.amount == Decimal("100.00000000")

    def test_buy_includes_fees_in_cost_basis(self) -> None:
        portfolio = make_portfolio()
        tx = make_buy(portfolio.id, INSTRUMENT_A, "10", "100", fees="50")
        portfolio.apply_transaction(tx)

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        # total cost = 10*100 + 50 = 1050, / 10 shares = 105/share
        assert holding.average_cost.amount == Decimal("105.00000000")

    def test_second_buy_computes_weighted_average(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "200"))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        # (10*100 + 10*200) / 20 = 3000/20 = 150
        assert holding.quantity.value == Decimal("20.00000000")
        assert holding.average_cost.amount == Decimal("150.00000000")

    def test_buys_in_different_instruments_create_separate_holdings(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_B, "5", "50"))

        assert portfolio.get_holding(INSTRUMENT_A) is not None
        assert portfolio.get_holding(INSTRUMENT_B) is not None
        assert len(portfolio.holdings) == 2


class TestApplySellTransaction:
    def test_sell_reduces_quantity_keeps_average_cost(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        result = portfolio.apply_transaction(make_sell(portfolio.id, INSTRUMENT_A, "4", "150"))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("6.00000000")
        assert holding.average_cost.amount == Decimal("100.00000000")  # unchanged
        assert result is not None
        assert result.gain.amount == Decimal("200.00000000")  # (150-100)*4

    def test_sell_with_fees_reduces_proceeds_and_gain(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        result = portfolio.apply_transaction(
            make_sell(portfolio.id, INSTRUMENT_A, "10", "150", fees="20")
        )

        assert result is not None
        # proceeds = 10*150 - 20 = 1480; cost_basis = 10*100 = 1000; gain = 480
        assert result.gain.amount == Decimal("480.00000000")

    def test_selling_more_than_held_raises(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "5", "100"))

        with pytest.raises(InsufficientHoldingQuantityError):
            portfolio.apply_transaction(make_sell(portfolio.id, INSTRUMENT_A, "10", "100"))

    def test_selling_from_nonexistent_holding_raises(self) -> None:
        portfolio = make_portfolio()
        with pytest.raises(InsufficientHoldingQuantityError):
            portfolio.apply_transaction(make_sell(portfolio.id, INSTRUMENT_A, "1", "100"))

    def test_selling_entire_position_leaves_zero_quantity(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_sell(portfolio.id, INSTRUMENT_A, "10", "150"))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.is_zero()


class TestApplySplitTransaction:
    def test_two_for_one_split_doubles_quantity_halves_cost(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_split(portfolio.id, INSTRUMENT_A, ratio=2.0))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("20.00000000")
        assert holding.average_cost.amount == Decimal("50.00000000")

    def test_split_preserves_total_cost_basis_within_rounding_tolerance(self) -> None:
        # A split ratio that doesn't divide evenly (e.g. 100/3 = 33.33...
        # repeating) cannot be represented exactly at any finite decimal
        # precision — storing average-cost-per-share is inherently lossy
        # for such ratios, same as real brokerage statements. We assert
        # the discrepancy is bounded by the smallest representable unit
        # (1e-8) per share times the new share count, not that it's zero.
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding_before = portfolio.get_holding(INSTRUMENT_A)
        assert holding_before is not None
        cost_before = holding_before.total_cost_basis()

        portfolio.apply_transaction(make_split(portfolio.id, INSTRUMENT_A, ratio=3.0))
        holding_after = portfolio.get_holding(INSTRUMENT_A)
        assert holding_after is not None
        max_rounding_error = Decimal("0.00000001") * holding_after.quantity.value
        actual_diff = abs(holding_after.total_cost_basis().amount - cost_before.amount)
        assert actual_diff <= max_rounding_error

    def test_split_with_exact_ratio_preserves_total_cost_basis_exactly(self) -> None:
        # When the ratio divides evenly, there is no excuse for any
        # rounding drift at all.
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding_before = portfolio.get_holding(INSTRUMENT_A)
        assert holding_before is not None
        cost_before = holding_before.total_cost_basis()

        portfolio.apply_transaction(make_split(portfolio.id, INSTRUMENT_A, ratio=2.0))
        holding_after = portfolio.get_holding(INSTRUMENT_A)
        assert holding_after is not None
        assert holding_after.total_cost_basis().amount == cost_before.amount

    def test_reverse_split_reduces_quantity(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        portfolio.apply_transaction(make_split(portfolio.id, INSTRUMENT_A, ratio=0.5))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("5.00000000")
        assert holding.average_cost.amount == Decimal("200.00000000")

    def test_split_on_nonexistent_holding_raises(self) -> None:
        portfolio = make_portfolio()
        with pytest.raises(InvalidTransactionError):
            portfolio.apply_transaction(make_split(portfolio.id, INSTRUMENT_A, ratio=2.0))


class TestApplyTransferTransactions:
    def test_transfer_in_creates_holding_with_cost_basis(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_transfer_in(portfolio.id, INSTRUMENT_A, "10", "100"))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("10.00000000")
        assert holding.average_cost.amount == Decimal("100.00000000")

    def test_transfer_in_does_not_return_realized_gain(self) -> None:
        portfolio = make_portfolio()
        result = portfolio.apply_transaction(
            make_transfer_in(portfolio.id, INSTRUMENT_A, "10", "100")
        )
        assert result is None

    def test_transfer_out_reduces_quantity_no_gain(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        result = portfolio.apply_transaction(make_transfer_out(portfolio.id, INSTRUMENT_A, "4"))

        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.quantity.value == Decimal("6.00000000")
        assert result is None  # no realized gain event for transfers

    def test_transfer_out_more_than_held_raises(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "5", "100"))
        with pytest.raises(InsufficientHoldingQuantityError):
            portfolio.apply_transaction(make_transfer_out(portfolio.id, INSTRUMENT_A, "10"))

    def test_transfer_out_from_nonexistent_holding_raises(self) -> None:
        portfolio = make_portfolio()
        with pytest.raises(InsufficientHoldingQuantityError):
            portfolio.apply_transaction(make_transfer_out(portfolio.id, INSTRUMENT_A, "1"))


class TestApplyDividendAndCashTransactions:
    def test_dividend_does_not_change_holding(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding_before = portfolio.get_holding(INSTRUMENT_A)
        assert holding_before is not None
        qty_before, cost_before = holding_before.quantity, holding_before.average_cost

        result = portfolio.apply_transaction(make_dividend(portfolio.id, INSTRUMENT_A, "25"))

        holding_after = portfolio.get_holding(INSTRUMENT_A)
        assert holding_after is not None
        assert holding_after.quantity.value == qty_before.value
        assert holding_after.average_cost.amount == cost_before.amount
        assert result is None

    def test_deposit_does_not_touch_holdings(self) -> None:
        portfolio = make_portfolio()
        result = portfolio.apply_transaction(make_deposit(portfolio.id, "1000"))
        assert result is None
        assert len(portfolio.holdings) == 0


class TestHoldingMarketValueCalculations:
    def test_market_value(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        assert holding.market_value(Money(Decimal("120"))).amount == Decimal("1200.00000000")

    def test_unrealized_gain_positive(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        gain = holding.unrealized_gain(Money(Decimal("120")))
        assert gain.amount == Decimal("200.00000000")  # (120-100)*10

    def test_unrealized_gain_negative(self) -> None:
        portfolio = make_portfolio()
        portfolio.apply_transaction(make_buy(portfolio.id, INSTRUMENT_A, "10", "100"))
        holding = portfolio.get_holding(INSTRUMENT_A)
        assert holding is not None
        gain = holding.unrealized_gain(Money(Decimal("80")))
        assert gain.amount == Decimal("-200.00000000")
