"""GetHistoricalPricesUseCase — a simplified close-price-only time series
(for a line chart), built on top of GetOhlcvBarsUseCase rather than
duplicating its fetch/persist/backfill logic. Distinct from the OHLCV API
per the founder's explicit separate "Historical Price API" vs "OHLCV API"
requirement — this returns (date, adjusted_close) pairs; OHLCV returns the
full bar (open/high/low/close/volume) for candlestick-style charting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.application.market_data.get_ohlcv_bars_use_case import GetOhlcvBarsUseCase
from src.domain.market_data.value_objects import Interval, Price


@dataclass(frozen=True, slots=True)
class PricePoint:
    as_of: datetime
    price: Price  # adjusted_close — correct for trend analysis, Document 5 §11.4


@dataclass(frozen=True, slots=True)
class HistoricalPricesResult:
    symbol: str
    interval: Interval
    points: tuple[PricePoint, ...]
    data_completeness: str


class GetHistoricalPricesUseCase:
    def __init__(self, get_ohlcv_bars_use_case: GetOhlcvBarsUseCase) -> None:
        self._get_ohlcv_bars_use_case = get_ohlcv_bars_use_case

    async def execute(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> HistoricalPricesResult:
        ohlcv_result = await self._get_ohlcv_bars_use_case.execute(symbol, interval, start, end)
        points = tuple(
            PricePoint(as_of=bar.bar_time, price=bar.adjusted_close) for bar in ohlcv_result.bars
        )
        return HistoricalPricesResult(
            symbol=symbol,
            interval=interval,
            points=points,
            data_completeness=ohlcv_result.data_completeness,
        )
