"""Domain entities for the market_data bounded context.

Per Document 3 §8.1 (instruments/ohlcv_bars/corporate_actions) and
Document 5 §11.4 (corporate action adjustment rules: "historical bars
before ex_date are NOT mutated in place... adjusted_close recalculated via
a backward-adjustment factor cascade whenever a new corporate action is
recorded").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from src.domain.market_data.exceptions import (
    InvalidCorporateActionError,
    InvalidOhlcvBarError,
)
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval, Price


class AssetType(str, Enum):
    """Per Document 3 §8.1's instruments.asset_type CHECK constraint."""

    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    CRYPTO = "crypto"


class CorporateActionType(str, Enum):
    """Per Document 3 §8.1's corporate_actions.action_type CHECK constraint."""

    SPLIT = "split"
    DIVIDEND = "dividend"
    SPINOFF = "spinoff"


@dataclass(slots=True)
class Instrument:
    """Per Document 3 §8.1's `instruments` table. The `id` field is
    intentionally typed as the shared InstrumentId (from
    src.domain.portfolio.value_objects) — see value_objects.py's
    module docstring for why this is not duplicated."""

    id: InstrumentId
    symbol: str
    exchange: str
    name: str
    asset_type: AssetType
    currency: str
    sector: str | None
    industry: str | None
    ipo_date: date | None
    is_active: bool
    created_at: datetime


@dataclass(slots=True)
class OhlcvBar:
    """Per Document 3 §8.1's `ohlcv_bars` table. Immutable once
    `is_closed=True` (Document 5 §11.2 stage 4: "Closed daily/intraday bar
    ... append-only, immutable once the bar period has closed") — this
    entity itself doesn't enforce that (it's a persistence-layer/use-case
    concern to never re-save a closed bar with different OHLC values), but
    `adjusted_close` IS expected to be recalculated in place when a new
    corporate action is recorded, per Document 5 §11.4 — that is the one
    documented exception to "never mutated."
    """

    instrument_id: InstrumentId
    interval: Interval
    bar_time: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    adjusted_close: Price
    volume: int
    is_closed: bool
    source: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.high.amount < self.low.amount:
            raise InvalidOhlcvBarError(f"high ({self.high}) cannot be less than low ({self.low})")
        if not (self.low.amount <= self.open.amount <= self.high.amount):
            raise InvalidOhlcvBarError(
                f"open ({self.open}) must be within [low, high] = [{self.low}, {self.high}]"
            )
        if not (self.low.amount <= self.close.amount <= self.high.amount):
            raise InvalidOhlcvBarError(
                f"close ({self.close}) must be within [low, high] = [{self.low}, {self.high}]"
            )
        if self.volume < 0:
            raise InvalidOhlcvBarError(f"volume cannot be negative, got {self.volume}")

    def with_adjusted_close(self, factor: Decimal) -> OhlcvBar:
        """Returns a NEW OhlcvBar with adjusted_close rescaled by `factor` —
        the backward-adjustment cascade from Document 5 §11.4. Only
        `adjusted_close` changes; raw open/high/low/close/volume are
        preserved exactly as originally recorded (the documented
        "historical bars are NOT mutated in place" rule applies to the raw
        OHLCV fields, not to adjusted_close, which exists specifically to
        be recalculated).
        """
        return OhlcvBar(
            instrument_id=self.instrument_id,
            interval=self.interval,
            bar_time=self.bar_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            adjusted_close=self.adjusted_close * factor,
            volume=self.volume,
            is_closed=self.is_closed,
            source=self.source,
            created_at=self.created_at,
        )


@dataclass(slots=True)
class CorporateAction:
    """Per Document 3 §8.1's `corporate_actions` table."""

    id: CorporateActionId
    instrument_id: InstrumentId
    action_type: CorporateActionType
    ratio: Decimal | None
    cash_amount: Price | None
    ex_date: date
    announced_at: datetime | None
    created_at: datetime

    def __post_init__(self) -> None:
        if self.action_type == CorporateActionType.SPLIT:
            if self.ratio is None or self.ratio <= 0:
                raise InvalidCorporateActionError(
                    "A 'split' corporate action requires a positive ratio"
                )
            if self.cash_amount is not None:
                raise InvalidCorporateActionError(
                    "A 'split' corporate action must not have a cash_amount"
                )
        elif self.action_type == CorporateActionType.DIVIDEND:
            if self.cash_amount is None:
                raise InvalidCorporateActionError(
                    "A 'dividend' corporate action requires a cash_amount"
                )
            if self.ratio is not None:
                raise InvalidCorporateActionError(
                    "A 'dividend' corporate action must not have a ratio"
                )
        elif self.action_type == CorporateActionType.SPINOFF:
            # Document 5 §11.4 doesn't specify spinoff's exact fields beyond
            # {instrument_id, action_type, ratio, ex_date, announced_at} —
            # ratio is the spinoff distribution ratio; cash_amount unused.
            if self.cash_amount is not None:
                raise InvalidCorporateActionError(
                    "A 'spinoff' corporate action must not have a cash_amount"
                )

    def backward_adjustment_factor(self) -> Decimal:
        """The factor applied to adjusted_close for all bars strictly
        before this action's ex_date, per Document 5 §11.4's backward-
        adjustment cascade. For a split, this is 1/ratio (e.g. a 2:1 split
        halves the pre-split adjusted price to make it comparable to
        post-split prices). Dividends/spinoffs do not affect price
        continuity the same way a split does — only 'split' actions
        produce a non-1.0 factor in this implementation; dividend/spinoff
        price-adjustment (total-return-style adjustment) is a documented
        simplification, not built in this phase (not in the founder's
        explicit Phase 4 requirement list — only OHLCV/quote/corporate-
        actions-as-data APIs were requested, not a total-return series).
        """
        if self.action_type == CorporateActionType.SPLIT:
            assert self.ratio is not None
            return Decimal("1") / self.ratio
        return Decimal("1")
