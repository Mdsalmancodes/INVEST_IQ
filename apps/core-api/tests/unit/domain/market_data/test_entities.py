"""Unit tests for Price value object and the OhlcvBar/CorporateAction
entities — the OHLC-consistency validation and the corporate-action
backward-adjustment factor are the highest-risk logic in this domain
package, so tested exhaustively."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.domain.market_data.entities import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    Instrument,
    OhlcvBar,
)
from src.domain.market_data.exceptions import (
    InvalidCorporateActionError,
    InvalidOhlcvBarError,
    InvalidPriceError,
)
from src.domain.market_data.value_objects import CorporateActionId, InstrumentId, Interval, Price

NOW = datetime(2026, 1, 1, tzinfo=UTC)
INSTRUMENT_ID = InstrumentId(uuid.uuid4())


class TestPrice:
    def test_constructs_from_decimal(self) -> None:
        assert Price(Decimal("100.50")).amount == Decimal("100.50000000")

    def test_rejects_float(self) -> None:
        with pytest.raises(InvalidPriceError):
            Price(100.5)  # type: ignore[arg-type]

    def test_rejects_negative(self) -> None:
        with pytest.raises(InvalidPriceError):
            Price(Decimal("-1"))

    def test_zero_is_allowed(self) -> None:
        # Some instruments (e.g. delisted, halted) can legitimately show 0.
        assert Price(Decimal("0")).amount == Decimal("0.00000000")

    def test_arithmetic(self) -> None:
        a = Price(Decimal("100"))
        b = Price(Decimal("50"))
        assert (a + b).amount == Decimal("150.00000000")
        assert (a - b).amount == Decimal("50.00000000")
        assert (a * Decimal("2")).amount == Decimal("200.00000000")
        assert (a / Decimal("2")).amount == Decimal("50.00000000")

    def test_comparison(self) -> None:
        assert Price(Decimal("50")) < Price(Decimal("100"))
        assert Price(Decimal("100")) > Price(Decimal("50"))
        assert Price(Decimal("50")) <= Price(Decimal("50"))
        assert Price(Decimal("50")) >= Price(Decimal("50"))


def make_bar(
    open_: str = "100",
    high: str = "110",
    low: str = "95",
    close: str = "105",
    adjusted_close: str = "105",
    volume: int = 1000,
) -> OhlcvBar:
    return OhlcvBar(
        instrument_id=INSTRUMENT_ID,
        interval=Interval.ONE_DAY,
        bar_time=NOW,
        open=Price(Decimal(open_)),
        high=Price(Decimal(high)),
        low=Price(Decimal(low)),
        close=Price(Decimal(close)),
        adjusted_close=Price(Decimal(adjusted_close)),
        volume=volume,
        is_closed=True,
        source="yfinance",
        created_at=NOW,
    )


class TestOhlcvBarValidation:
    def test_valid_bar_constructs(self) -> None:
        bar = make_bar()
        assert bar.close.amount == Decimal("105.00000000")

    def test_rejects_high_less_than_low(self) -> None:
        with pytest.raises(InvalidOhlcvBarError):
            make_bar(high="90", low="95")

    def test_rejects_open_outside_high_low_range(self) -> None:
        with pytest.raises(InvalidOhlcvBarError):
            make_bar(open_="200", high="110", low="95")

    def test_rejects_close_outside_high_low_range(self) -> None:
        with pytest.raises(InvalidOhlcvBarError):
            make_bar(close="5", high="110", low="95")

    def test_rejects_negative_volume(self) -> None:
        with pytest.raises(InvalidOhlcvBarError):
            make_bar(volume=-1)

    def test_open_equal_to_high_is_valid(self) -> None:
        bar = make_bar(open_="110", high="110", low="95", close="100")
        assert bar.open.amount == Decimal("110.00000000")

    def test_open_equal_to_low_is_valid(self) -> None:
        bar = make_bar(open_="95", high="110", low="95", close="100")
        assert bar.open.amount == Decimal("95.00000000")


class TestOhlcvBarAdjustment:
    def test_with_adjusted_close_rescales_only_adjusted_close(self) -> None:
        bar = make_bar(adjusted_close="105")
        adjusted = bar.with_adjusted_close(Decimal("0.5"))

        assert adjusted.adjusted_close.amount == Decimal("52.50000000")
        # raw OHLCV fields are preserved exactly
        assert adjusted.open == bar.open
        assert adjusted.high == bar.high
        assert adjusted.low == bar.low
        assert adjusted.close == bar.close
        assert adjusted.volume == bar.volume

    def test_with_adjusted_close_returns_new_instance(self) -> None:
        bar = make_bar()
        adjusted = bar.with_adjusted_close(Decimal("1"))
        assert adjusted is not bar


def make_split(ratio: str = "2.0") -> CorporateAction:
    return CorporateAction(
        id=CorporateActionId.new(),
        instrument_id=INSTRUMENT_ID,
        action_type=CorporateActionType.SPLIT,
        ratio=Decimal(ratio),
        cash_amount=None,
        ex_date=date(2026, 1, 1),
        announced_at=NOW,
        created_at=NOW,
    )


def make_dividend(amount: str = "1.50") -> CorporateAction:
    return CorporateAction(
        id=CorporateActionId.new(),
        instrument_id=INSTRUMENT_ID,
        action_type=CorporateActionType.DIVIDEND,
        ratio=None,
        cash_amount=Price(Decimal(amount)),
        ex_date=date(2026, 1, 1),
        announced_at=NOW,
        created_at=NOW,
    )


class TestCorporateActionValidation:
    def test_valid_split_constructs(self) -> None:
        action = make_split("2.0")
        assert action.ratio == Decimal("2.0")

    def test_split_without_ratio_raises(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            CorporateAction(
                id=CorporateActionId.new(),
                instrument_id=INSTRUMENT_ID,
                action_type=CorporateActionType.SPLIT,
                ratio=None,
                cash_amount=None,
                ex_date=date(2026, 1, 1),
                announced_at=None,
                created_at=NOW,
            )

    def test_split_with_zero_ratio_raises(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            make_split("0")

    def test_split_with_cash_amount_raises(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            CorporateAction(
                id=CorporateActionId.new(),
                instrument_id=INSTRUMENT_ID,
                action_type=CorporateActionType.SPLIT,
                ratio=Decimal("2"),
                cash_amount=Price(Decimal("1")),
                ex_date=date(2026, 1, 1),
                announced_at=None,
                created_at=NOW,
            )

    def test_valid_dividend_constructs(self) -> None:
        action = make_dividend("1.50")
        assert action.cash_amount is not None
        assert action.cash_amount.amount == Decimal("1.50000000")

    def test_dividend_without_cash_amount_raises(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            CorporateAction(
                id=CorporateActionId.new(),
                instrument_id=INSTRUMENT_ID,
                action_type=CorporateActionType.DIVIDEND,
                ratio=None,
                cash_amount=None,
                ex_date=date(2026, 1, 1),
                announced_at=None,
                created_at=NOW,
            )

    def test_dividend_with_ratio_raises(self) -> None:
        with pytest.raises(InvalidCorporateActionError):
            CorporateAction(
                id=CorporateActionId.new(),
                instrument_id=INSTRUMENT_ID,
                action_type=CorporateActionType.DIVIDEND,
                ratio=Decimal("2"),
                cash_amount=Price(Decimal("1")),
                ex_date=date(2026, 1, 1),
                announced_at=None,
                created_at=NOW,
            )


class TestBackwardAdjustmentFactor:
    def test_two_for_one_split_factor_is_half(self) -> None:
        action = make_split("2.0")
        assert action.backward_adjustment_factor() == Decimal("0.5")

    def test_three_for_one_split_factor(self) -> None:
        action = make_split("3.0")
        assert action.backward_adjustment_factor() == Decimal("1") / Decimal("3")

    def test_reverse_split_factor_greater_than_one(self) -> None:
        # 1-for-2 reverse split: ratio 0.5 -> factor 1/0.5 = 2.0
        action = make_split("0.5")
        assert action.backward_adjustment_factor() == Decimal("2")

    def test_dividend_factor_is_one(self) -> None:
        action = make_dividend("1.50")
        assert action.backward_adjustment_factor() == Decimal("1")


class TestInstrument:
    def test_constructs_with_all_fields(self) -> None:
        instrument = Instrument(
            id=INSTRUMENT_ID,
            symbol="AAPL",
            exchange="NASDAQ",
            name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            currency="USD",
            sector="Technology",
            industry="Consumer Electronics",
            ipo_date=date(1980, 12, 12),
            is_active=True,
            created_at=NOW,
        )
        assert instrument.symbol == "AAPL"
        assert instrument.asset_type == AssetType.EQUITY

    def test_ipo_date_can_be_none(self) -> None:
        instrument = Instrument(
            id=INSTRUMENT_ID,
            symbol="NEWCO",
            exchange="NASDAQ",
            name="New Co",
            asset_type=AssetType.EQUITY,
            currency="USD",
            sector=None,
            industry=None,
            ipo_date=None,
            is_active=True,
            created_at=NOW,
        )
        assert instrument.ipo_date is None
