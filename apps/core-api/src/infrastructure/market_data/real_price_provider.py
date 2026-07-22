"""RealPriceProvider — implements Portfolio's PriceProvider Protocol
(src.application.portfolio.price_provider.PriceProvider), backed by the
Market Data Foundation's OhlcvBarRepository. This is the upgrade
NullPriceProvider's own docstring specified exactly: "once Document 8 §24
is implemented, replace this class with one backed by ohlcv_bars (latest
closed bar = current price, previous trading day's close =
previous_close) — no change needed to PortfolioCalculationService or any
use case, since they only depend on the PriceProvider Protocol."

Per Portfolio's PriceProvider contract: returns None (never raises) when
no price is available, so PortfolioCalculationService's existing
graceful-degradation logic (holdings_missing_price) continues to work
unchanged for instruments this phase's market data hasn't covered yet.
"""

from __future__ import annotations

from src.domain.market_data.repositories import OhlcvBarQuery, OhlcvBarRepository
from src.domain.market_data.value_objects import Interval
from src.domain.portfolio.value_objects import InstrumentId, Money


class RealPriceProvider:
    def __init__(self, ohlcv_bar_repository: OhlcvBarRepository) -> None:
        self._ohlcv_bar_repository = ohlcv_bar_repository

    async def get_current_price(self, instrument_id: InstrumentId) -> Money | None:
        # Portfolio's InstrumentId and market_data's InstrumentId are the
        # SAME type (src.domain.portfolio.value_objects.InstrumentId,
        # re-exported by src.domain.market_data.value_objects — see that
        # module's docstring) so no conversion is needed here at all.
        latest_bar = await self._ohlcv_bar_repository.get_latest_closed_bar(
            instrument_id, Interval.ONE_DAY
        )
        if latest_bar is None:
            return None
        return Money(latest_bar.adjusted_close.amount)

    async def get_previous_close(self, instrument_id: InstrumentId) -> Money | None:
        # "Previous close" for Daily Gain/Loss purposes is the second-most-
        # recent closed daily bar (the most recent IS "today's" close,
        # i.e. current_price above) — Document 5 §11.4's adjusted_close
        # is used here too, for the same trend-continuity reason. Query
        # the last 2 bars (ordered ascending by bar_time, per
        # OhlcvBarRepository.query's documented contract) and take the
        # second-to-last.
        query = OhlcvBarQuery(instrument_id=instrument_id, interval=Interval.ONE_DAY)
        bars = await self._ohlcv_bar_repository.query(query)
        if len(bars) < 2:
            return None
        last_two = bars[-2:]
        return Money(last_two[0].adjusted_close.amount)
