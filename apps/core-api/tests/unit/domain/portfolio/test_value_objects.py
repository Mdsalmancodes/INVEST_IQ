"""Unit tests for Money and Quantity value objects — Document 6 §16.2's
domain-layer coverage target (95%+), and these two types underpin every
financial calculation in Phase 3, so they are tested exhaustively."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.portfolio.exceptions import InvalidMoneyAmountError, InvalidQuantityError
from src.domain.portfolio.value_objects import Money, Quantity


class TestMoneyConstruction:
    def test_constructs_from_decimal(self) -> None:
        assert Money(Decimal("100.50")).amount == Decimal("100.50000000")

    def test_rejects_construction_from_float(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(100.50)  # type: ignore[arg-type]

    def test_rejects_construction_from_int(self) -> None:
        with pytest.raises(InvalidMoneyAmountError):
            Money(100)  # type: ignore[arg-type]

    def test_quantizes_to_8_decimal_places(self) -> None:
        money = Money(Decimal("1.123456789"))
        assert money.amount == Decimal("1.12345679")  # rounded half-up

    def test_zero_factory(self) -> None:
        assert Money.zero().amount == Decimal("0.00000000")


class TestMoneyArithmetic:
    def test_addition(self) -> None:
        result = Money(Decimal("100")) + Money(Decimal("50"))
        assert result.amount == Decimal("150.00000000")

    def test_subtraction(self) -> None:
        result = Money(Decimal("100")) - Money(Decimal("30"))
        assert result.amount == Decimal("70.00000000")

    def test_subtraction_can_go_negative(self) -> None:
        # Unlike Quantity, Money legitimately CAN be negative (e.g. a
        # realized loss, or a cash balance overdraft) — no guard here.
        result = Money(Decimal("30")) - Money(Decimal("100"))
        assert result.amount == Decimal("-70.00000000")

    def test_multiplication(self) -> None:
        result = Money(Decimal("10.5")) * Decimal("3")
        assert result.amount == Decimal("31.50000000")

    def test_is_negative(self) -> None:
        assert Money(Decimal("-5")).is_negative() is True
        assert Money(Decimal("5")).is_negative() is False
        assert Money.zero().is_negative() is False


class TestMoneyComparison:
    def test_less_than(self) -> None:
        assert Money(Decimal("5")) < Money(Decimal("10"))
        assert not (Money(Decimal("10")) < Money(Decimal("5")))

    def test_less_than_or_equal(self) -> None:
        assert Money(Decimal("5")) <= Money(Decimal("5"))

    def test_greater_than(self) -> None:
        assert Money(Decimal("10")) > Money(Decimal("5"))

    def test_greater_than_or_equal(self) -> None:
        assert Money(Decimal("5")) >= Money(Decimal("5"))

    def test_equality(self) -> None:
        assert Money(Decimal("5")) == Money(Decimal("5.00"))


class TestQuantityConstruction:
    def test_constructs_from_decimal(self) -> None:
        assert Quantity(Decimal("10")).value == Decimal("10.00000000")

    def test_rejects_construction_from_float(self) -> None:
        with pytest.raises(InvalidQuantityError):
            Quantity(10.5)  # type: ignore[arg-type]

    def test_rejects_negative_quantity(self) -> None:
        with pytest.raises(InvalidQuantityError):
            Quantity(Decimal("-1"))

    def test_zero_factory(self) -> None:
        assert Quantity.zero().value == Decimal("0.00000000")

    def test_supports_fractional_shares(self) -> None:
        # Real scenario: DRIP dividend reinvestment produces fractional shares.
        assert Quantity(Decimal("0.12345678")).value == Decimal("0.12345678")


class TestQuantityArithmetic:
    def test_addition(self) -> None:
        result = Quantity(Decimal("10")) + Quantity(Decimal("5"))
        assert result.value == Decimal("15.00000000")

    def test_subtraction(self) -> None:
        result = Quantity(Decimal("10")) - Quantity(Decimal("3"))
        assert result.value == Decimal("7.00000000")

    def test_subtraction_below_zero_raises(self) -> None:
        # Document 3 §3.4 rule #1: a Portfolio aggregate must never allow a
        # holding's quantity to go negative — enforced here at the value
        # object level as the innermost guard.
        with pytest.raises(InvalidQuantityError):
            Quantity(Decimal("5")) - Quantity(Decimal("10"))

    def test_subtraction_to_exactly_zero_is_allowed(self) -> None:
        result = Quantity(Decimal("10")) - Quantity(Decimal("10"))
        assert result.is_zero() is True

    def test_multiplication(self) -> None:
        # Used for split adjustments (ADR-0003): e.g. quantity * 2 for a 2:1 split.
        result = Quantity(Decimal("100")) * Decimal("2")
        assert result.value == Decimal("200.00000000")

    def test_is_zero(self) -> None:
        assert Quantity.zero().is_zero() is True
        assert Quantity(Decimal("0.00000001")).is_zero() is False
