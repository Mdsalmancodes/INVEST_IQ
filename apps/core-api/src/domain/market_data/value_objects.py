"""Value objects for the market_data bounded context.

Per Document 3 §3.4's Decimal-never-float rule (already applied identically
in src.domain.portfolio.value_objects.Money) — prices/volumes here follow
the same discipline. `InstrumentId` is intentionally NOT duplicated here;
it already exists in src.domain.portfolio.value_objects (Portfolio
references instruments by id) and is imported from there, since splitting
one conceptual id type across two modules would be a worse outcome than a
single cross-context import of a plain value object.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from src.domain.market_data.exceptions import InvalidIntervalError, InvalidPriceError
from src.domain.portfolio.value_objects import InstrumentId  # re-exported below

__all__ = ["InstrumentId", "CorporateActionId", "Interval", "Price"]

_QUANTIZE_UNIT = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class CorporateActionId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> CorporateActionId:
        return cls(uuid.uuid4())

    @classmethod
    def from_string(cls, raw: str) -> CorporateActionId:
        return cls(uuid.UUID(raw))

    def __str__(self) -> str:
        return str(self.value)


class Interval(str, Enum):
    """Per Document 3 §8.1's ohlcv_bars.interval CHECK constraint."""

    ONE_MINUTE = "1min"
    FIVE_MINUTE = "5min"
    FIFTEEN_MINUTE = "15min"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"

    @classmethod
    def from_string(cls, raw: str) -> Interval:
        try:
            return cls(raw)
        except ValueError as exc:
            raise InvalidIntervalError(f"Unknown interval: {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class Price:
    """Decimal-backed price value — same discipline as
    src.domain.portfolio.value_objects.Money, kept as a distinct type
    (not a reuse of Money) since a market price is conceptually a
    per-instrument market fact, not a portfolio monetary amount, even
    though the underlying representation is identical. Quantized to 8
    decimal places to match the NUMERIC(20,8) columns it round-trips with.
    """

    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise InvalidPriceError(
                f"Price must be constructed from a Decimal, got {type(self.amount).__name__}"
            )
        if self.amount < Decimal("0"):
            raise InvalidPriceError(f"Price cannot be negative, got {self.amount}")
        quantized = self.amount.quantize(_QUANTIZE_UNIT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    def __add__(self, other: Price) -> Price:
        return Price(self.amount + other.amount)

    def __sub__(self, other: Price) -> Price:
        return Price(self.amount - other.amount)

    def __mul__(self, multiplier: Decimal) -> Price:
        return Price(self.amount * multiplier)

    def __truediv__(self, divisor: Decimal) -> Price:
        return Price(self.amount / divisor)

    def __lt__(self, other: Price) -> bool:
        return self.amount < other.amount

    def __le__(self, other: Price) -> bool:
        return self.amount <= other.amount

    def __gt__(self, other: Price) -> bool:
        return self.amount > other.amount

    def __ge__(self, other: Price) -> bool:
        return self.amount >= other.amount

    def __str__(self) -> str:
        return str(self.amount)
