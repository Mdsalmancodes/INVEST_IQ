"""GetOhlcvBarsUseCase — the full OHLCV bar series for an instrument,
reading from Postgres (never live-fetching from a provider on every
request — that's the background sync job's, task 7, responsibility to
keep the table populated). Falls back to a live provider fetch ONLY if
the database has no coverage at all for the requested range, so a
first-time symbol request doesn't return empty (Document 5 §11.3's
historical-backfill-on-first-request behavior), persisting what it fetches
so subsequent requests are served from Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.application.market_data.instrument_resolution import get_instrument_by_symbol_or_raise
from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.validation_service import MarketDataValidationService
from src.domain.market_data.entities import OhlcvBar
from src.domain.market_data.repositories import (
    InstrumentRepository,
    OhlcvBarQuery,
    OhlcvBarRepository,
)
from src.domain.market_data.value_objects import Interval


@dataclass(frozen=True, slots=True)
class OhlcvBarsResult:
    symbol: str
    interval: Interval
    bars: tuple[OhlcvBar, ...]
    data_completeness: str  # "complete" | "partial" - Document 5 §11.3's dataCompleteness field


class GetOhlcvBarsUseCase:
    def __init__(
        self,
        instrument_repository: InstrumentRepository,
        ohlcv_bar_repository: OhlcvBarRepository,
        provider_router: ProviderRouter,
        validation_service: MarketDataValidationService,
    ) -> None:
        self._instrument_repository = instrument_repository
        self._ohlcv_bar_repository = ohlcv_bar_repository
        self._provider_router = provider_router
        self._validation_service = validation_service

    async def execute(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> OhlcvBarsResult:
        instrument = await get_instrument_by_symbol_or_raise(self._instrument_repository, symbol)

        query = OhlcvBarQuery(
            instrument_id=instrument.id,
            interval=interval,
            start=datetime.combine(start, datetime.min.time()),
            end=datetime.combine(end, datetime.max.time()),
        )
        existing_bars = await self._ohlcv_bar_repository.query(query)
        if existing_bars:
            return OhlcvBarsResult(
                symbol=symbol, interval=interval, bars=existing_bars, data_completeness="complete"
            )

        # No coverage at all — Document 5 §11.3's "when a symbol is
        # requested for the first time... fetch historical range from
        # provider... API returns available data immediately (even if
        # partial)". This phase fetches synchronously rather than
        # enqueuing a Celery backfill task and returning partial data
        # immediately (the frozen architecture's stated non-blocking
        # behavior) — a disclosed simplification: the founder's Phase 4
        # scope asks for the APIs to work correctly, and a synchronous
        # fetch-on-first-request is correct (if slower on that one
        # request) without needing the full async-backfill-with-partial-
        # response UX this phase doesn't build.
        raw_bars = await self._provider_router.resolve_bars(symbol, interval, start, end)
        valid_bars = tuple(
            bar for bar in raw_bars if self._validation_service.validate_bar(bar).is_valid
        )
        deduped_bars = self._validation_service.dedupe_bars(valid_bars)

        domain_bars = tuple(
            OhlcvBar(
                instrument_id=instrument.id,
                interval=bar.interval,
                bar_time=bar.bar_time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                adjusted_close=bar.close,  # no corporate action adjustment applied yet
                volume=bar.volume,
                is_closed=bar.is_closed,
                source=bar.source,
                created_at=bar.bar_time,
            )
            for bar in deduped_bars
        )
        if domain_bars:
            await self._ohlcv_bar_repository.save_many(domain_bars)

        completeness = "complete" if len(domain_bars) == len(raw_bars) else "partial"
        return OhlcvBarsResult(
            symbol=symbol, interval=interval, bars=domain_bars, data_completeness=completeness
        )
