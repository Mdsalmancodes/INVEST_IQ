"""Unit tests for MarketDataValidationService — Document 5 §11.2 stage 2's
validate/dedupe rules, the safety-critical gate between provider data and
persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.application.market_data.provider import BarResult, QuoteResult
from src.application.market_data.validation_service import MarketDataValidationService
from src.domain.market_data.value_objects import Interval, Price

NOW = datetime(2026, 1, 1, tzinfo=UTC)
service = MarketDataValidationService()


def make_quote(price: str = "100", previous_close: str | None = "95") -> QuoteResult:
    return QuoteResult(
        symbol="AAPL",
        price=Price(Decimal(price)),
        previous_close=Price(Decimal(previous_close)) if previous_close else None,
        as_of=NOW,
        source="test",
    )


def make_bar(
    open_: str = "100",
    high: str = "110",
    low: str = "95",
    close: str = "105",
    volume: int = 1000,
) -> BarResult:
    return BarResult(
        symbol="AAPL",
        interval=Interval.ONE_DAY,
        bar_time=NOW,
        open=Price(Decimal(open_)),
        high=Price(Decimal(high)),
        low=Price(Decimal(low)),
        close=Price(Decimal(close)),
        volume=volume,
        is_closed=True,
        source="test",
    )


class TestValidateQuote:
    def test_valid_quote_passes(self) -> None:
        result = service.validate_quote(make_quote())
        assert result.is_valid is True

    def test_zero_price_is_rejected(self) -> None:
        # Price value object already rejects negative, but 0 is technically
        # allowed there (e.g. halted stock) — the validation service's own
        # business rule is stricter: reject non-positive for a QUOTE
        # specifically (as opposed to a historical bar showing a genuine
        # halt/delisting day, which is a different context).
        result = service.validate_quote(make_quote(price="0"))
        assert result.is_valid is False
        assert result.rejection_reason is not None

    def test_missing_previous_close_is_valid(self) -> None:
        result = service.validate_quote(make_quote(previous_close=None))
        assert result.is_valid is True


class TestValidateBar:
    def test_valid_bar_passes(self) -> None:
        result = service.validate_bar(make_bar())
        assert result.is_valid is True

    def test_zero_open_is_rejected(self) -> None:
        result = service.validate_bar(make_bar(open_="0"))
        assert result.is_valid is False

    def test_high_less_than_low_is_rejected(self) -> None:
        result = service.validate_bar(make_bar(high="90", low="95"))
        assert result.is_valid is False
        assert result.rejection_reason is not None and "low" in result.rejection_reason

    def test_open_outside_range_is_rejected(self) -> None:
        result = service.validate_bar(make_bar(open_="200", high="110", low="95"))
        assert result.is_valid is False

    def test_close_outside_range_is_rejected(self) -> None:
        result = service.validate_bar(make_bar(close="5", high="110", low="95"))
        assert result.is_valid is False

    def test_negative_volume_is_rejected(self) -> None:
        result = service.validate_bar(make_bar(volume=-1))
        assert result.is_valid is False

    def test_volume_within_normal_range_passes_with_reference(self) -> None:
        result = service.validate_bar(make_bar(volume=5000), reference_average_volume=1000)
        assert result.is_valid is True

    def test_volume_anomaly_beyond_threshold_is_rejected(self) -> None:
        # 50x the reference average (1000) = 50000; anything beyond that
        # is flagged as a vendor-glitch-style anomaly.
        result = service.validate_bar(make_bar(volume=100_000), reference_average_volume=1000)
        assert result.is_valid is False
        assert result.rejection_reason is not None and "anomaly" in result.rejection_reason

    def test_no_reference_volume_skips_anomaly_check(self) -> None:
        result = service.validate_bar(make_bar(volume=10_000_000), reference_average_volume=None)
        assert result.is_valid is True


class TestDedupeBars:
    def test_no_duplicates_returns_all(self) -> None:
        bar1 = make_bar(close="100")
        bar2 = BarResult(
            symbol="AAPL",
            interval=Interval.ONE_DAY,
            bar_time=datetime(2026, 1, 2, tzinfo=UTC),
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="test",
        )
        result = service.dedupe_bars((bar1, bar2))
        assert len(result) == 2

    def test_duplicate_key_keeps_last_occurrence(self) -> None:
        bar_v1 = make_bar(close="100")
        bar_v2 = make_bar(close="105")  # same symbol/bar_time/source, different close
        result = service.dedupe_bars((bar_v1, bar_v2))
        assert len(result) == 1
        assert result[0].close.amount == Decimal("105.00000000")

    def test_different_source_is_not_deduped(self) -> None:
        bar_a = make_bar()
        bar_b = BarResult(
            symbol="AAPL",
            interval=Interval.ONE_DAY,
            bar_time=NOW,
            open=Price(Decimal("100")),
            high=Price(Decimal("110")),
            low=Price(Decimal("95")),
            close=Price(Decimal("105")),
            volume=1000,
            is_closed=True,
            source="different_vendor",
        )
        result = service.dedupe_bars((bar_a, bar_b))
        assert len(result) == 2
