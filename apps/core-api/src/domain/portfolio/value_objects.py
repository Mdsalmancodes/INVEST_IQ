"""Value objects for the portfolio bounded context.

Per docs/architecture/03-backend-architecture-database-design.md §3.4 rule
#2 ("Money is never a float... using Decimal, never IEEE floats — non-
negotiable for financial correctness") and Document 8 §20.2: value objects
are plain dataclasses, self-validating in __post_init__.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from src.domain.portfolio.exceptions import InvalidMoneyAmountError, InvalidQuantityError

_QUANTIZE_UNIT = Decimal("0.00000001")  # 8 decimal places, matches NUMERIC(20,8) columns


@dataclass(frozen=True, slots=True)
class PortfolioId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> PortfolioId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> PortfolioId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class HoldingId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> HoldingId:
        return cls(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TransactionId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> TransactionId:
        return cls(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Wraps the Postgres `instruments.id` UUID (Document 3 §8.1) — the
    Portfolio context references instruments by id, never by bare symbol,
    per the review-identified dual-listing ambiguity fix already applied to
    the instruments table's global-unique-symbol partial index."""

    value: uuid.UUID

    @classmethod
    def from_string(cls, raw: str) -> InstrumentId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Money:
    """Decimal-backed monetary value — Document 3 §3.4 rule #2. Quantized
    to 8 decimal places to match the NUMERIC(20,8) columns it round-trips
    with, so no precision is silently gained/lost between domain and
    persistence layers.
    """

    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvalidMoneyAmountError(
                f"Money must be constructed from a Decimal, got {type(self.amount).__name__}"
            )
        quantized = self.amount.quantize(_QUANTIZE_UNIT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    @classmethod
    def zero(cls) -> Money:
        return cls(Decimal("0"))

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        return Money(self.amount - other.amount)

    def __mul__(self, multiplier: Decimal) -> Money:
        return Money(self.amount * multiplier)

    def __lt__(self, other: Money) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        return self.amount >= other.amount

    def is_negative(self) -> bool:
        return self.amount < Decimal("0")

    def __str__(self) -> str:
        return str(self.amount)


@dataclass(frozen=True, slots=True)
class Quantity:
    """A share/unit count — Decimal-backed for the same reason as Money
    (fractional shares are real, e.g. DRIP dividend reinvestment), never
    negative (a negative "quantity" is a domain-logic error, not a valid
    state — represented instead via transaction `type`, e.g. `sell`)."""

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise InvalidQuantityError(
                f"Quantity must be constructed from a Decimal, got {type(self.value).__name__}"
            )
        if self.value < Decimal("0"):
            raise InvalidQuantityError(f"Quantity cannot be negative, got {self.value}")
        quantized = self.value.quantize(_QUANTIZE_UNIT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "value", quantized)

    @classmethod
    def zero(cls) -> Quantity:
        return cls(Decimal("0"))

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(self.value + other.value)

    def __sub__(self, other: Quantity) -> Quantity:
        result = self.value - other.value
        if result < Decimal("0"):
            raise InvalidQuantityError(
                f"Resulting quantity would be negative: {self.value} - {other.value}"
            )
        return Quantity(result)

    def __mul__(self, multiplier: Decimal) -> Quantity:
        return Quantity(self.value * multiplier)

    def is_zero(self) -> bool:
        return self.value == Decimal("0")

    def __str__(self) -> str:
        return str(self.value)
