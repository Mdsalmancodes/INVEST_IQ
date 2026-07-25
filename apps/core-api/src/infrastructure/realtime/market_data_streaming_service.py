"""MarketDataStreamingService — Phase 9's "Live Stock Data" requirement:
price/OHLC/volume/daily-high/daily-low/market-status/change/%change/
index values, streamed over WebSocket without a page refresh.

WHY A POLLING LOOP, NOT A CELERY TASK: this needs (a) a short interval
(config.py's realtime_market_data_poll_interval_seconds, default 5s) far
tighter than Celery beat's typical granularity is designed for, and (b)
direct in-process access to ConnectionManager.all_subscribed_topics() to
know exactly which symbols are worth polling right now — a Celery task
runs in a separate worker process/thread with no visibility into this
process's live WebSocket connections. An asyncio background task
(started in main.py's lifespan alongside RealtimeService) is the
correct mechanism, not a deviation from the existing Celery-based
Phase 4 sync_instrument_bars task, which remains unchanged and serves a
different purpose (daily historical backfill, not live ticks).

WHY POLLING AT ALL (not genuine push/streaming from the data provider):
no continuous/streaming market data provider exists in this dev
environment — yfinance (Document 5 §11.1) is a polling API, the same
disclosed limitation Phase 4's own background sync task already
carries. "Live" here means "polled frequently enough to feel live," not
a literal exchange-side push feed — disclosed here and in
docs/phase-9/known-issues.md, not silently implied to be something it
isn't.

Each tick, for every symbol currently subscribed to by ANY connected
client (ConnectionManager.all_subscribed_topics(), filtered to
"quote:SYMBOL" topics): calls the EXISTING GetCurrentPriceUseCase
(Phase 4, unmodified) for the live price, and the latest closed OHLCV
bar (via the EXISTING OhlcvBarRepository, also unmodified) for
OHLC/volume/daily-high/daily-low — computing change/%change against the
previous close either the quote or the bar provides. Market status
(open/closed session) reuses the EXISTING GetMarketStatusUseCase
(Phase 4) and is published once per tick on the market-wide ticker
channel, not per-symbol (session status is the same for every US-equity
symbol at any given moment, so recomputing it per-symbol would be pure
waste).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from decimal import Decimal

from observability import get_logger

from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.market_data.provider_router import ProviderRouter
from src.domain.market_data.repositories import InstrumentRepository, OhlcvBarRepository
from src.domain.market_data.value_objects import Interval
from src.infrastructure.market_data.cache import MarketDataCache
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker

logger = get_logger(__name__)

RepositoryFactory = Callable[[object], tuple[InstrumentRepository, OhlcvBarRepository]]
"""Given a session (or any session-like object the factory knows how to
use), returns (instrument_repository, ohlcv_bar_repository) — kept as a
plain Callable rather than importing the concrete SQLAlchemy repository
classes directly into this module, so tests can substitute fakes without
a real database session at all. Production wiring (main.py's lifespan)
passes a factory that constructs the real SqlAlchemy* repositories."""


@dataclass(frozen=True, slots=True)
class QuoteTick:
    """The published payload shape for a single symbol's tick — every
    field explicitly named in the founder's "Live Stock Data" list."""

    symbol: str
    price: str
    open: str | None
    high: str | None
    low: str | None
    volume: int | None
    previous_close: str | None
    change: str | None
    change_pct: str | None
    is_stale_fallback: bool


def _quote_symbols_from_topics(topics: frozenset[str]) -> frozenset[str]:
    return frozenset(
        topic.removeprefix("quote:") for topic in topics if topic.startswith("quote:")
    )


def _compute_change(
    price: Decimal, previous_close: Decimal | None
) -> tuple[str | None, str | None]:
    if previous_close is None or previous_close == 0:
        return None, None
    change = price - previous_close
    change_pct = (change / previous_close) * Decimal(100)
    return str(change), str(change_pct)


class MarketDataStreamingService:
    def __init__(
        self,
        connection_manager: ConnectionManager,
        redis_broker: RedisBroker,
        session_scope: Callable[[], AbstractAsyncContextManager[object]],
        repository_factory: RepositoryFactory,
        provider_router: ProviderRouter,
        market_data_cache: MarketDataCache,
        market_status_use_case: GetMarketStatusUseCase,
        poll_interval_seconds: float,
    ) -> None:
        self._connection_manager = connection_manager
        self._redis_broker = redis_broker
        self._session_scope = session_scope
        self._repository_factory = repository_factory
        self._provider_router = provider_router
        self._market_data_cache = market_data_cache
        self._market_status_use_case = market_status_use_case
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001 - one bad tick must
                # never kill the whole streaming loop; the next tick,
                # poll_interval_seconds later, gets a fresh chance.
                logger.warning("realtime.market_data.tick_failed", error=str(exc))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)

    async def tick(self) -> None:
        """Runs exactly one poll cycle — public so tests can invoke a
        single tick deterministically rather than driving the whole
        start()/stop() loop. Opens a FRESH DB session for this tick only
        (via session_scope(), never holding one open across the whole
        background loop's lifetime, matching every request-scoped
        session's lifecycle elsewhere in this codebase — a long-lived
        session would risk serving stale reads under Postgres's default
        isolation and leaking a connection from the pool indefinitely)."""
        symbols = _quote_symbols_from_topics(self._connection_manager.all_subscribed_topics())

        market_status = self._market_status_use_case.execute()
        await self._redis_broker.publish(
            channels.TICKER_CHANNEL,
            {
                "is_open": market_status.is_open,
                "session": market_status.session,
                "as_of": market_status.as_of.isoformat(),
            },
        )

        if not symbols:
            return

        async with self._session_scope() as session:
            instrument_repository, ohlcv_bar_repository = self._repository_factory(session)
            get_current_price_use_case = GetCurrentPriceUseCase(
                instrument_repository,
                ohlcv_bar_repository,
                self._provider_router,
                self._market_data_cache,
            )
            for symbol in symbols:
                tick = await self._build_quote_tick(
                    symbol, get_current_price_use_case, instrument_repository, ohlcv_bar_repository
                )
                if tick is None:
                    continue
                await self._redis_broker.publish(
                    channels.quote_channel(symbol), _tick_to_payload(tick)
                )

    async def _build_quote_tick(
        self,
        symbol: str,
        get_current_price_use_case: GetCurrentPriceUseCase,
        instrument_repository: InstrumentRepository,
        ohlcv_bar_repository: OhlcvBarRepository,
    ) -> QuoteTick | None:
        try:
            price_result = await get_current_price_use_case.execute(symbol)
        except Exception as exc:  # noqa: BLE001 - isolate one symbol's
            # failure (unknown symbol, every provider down, etc.) from
            # every other subscribed symbol's tick this cycle — matches
            # WatchlistEnrichmentService's Phase 5 per-item isolation.
            logger.warning("realtime.market_data.quote_failed", symbol=symbol, error=str(exc))
            return None

        instrument = await instrument_repository.get_by_symbol(symbol)
        bar = None
        if instrument is not None:
            bar = await ohlcv_bar_repository.get_latest_closed_bar(instrument.id, Interval.ONE_DAY)

        previous_close = (
            price_result.previous_close.amount if price_result.previous_close is not None else None
        )
        change, change_pct = _compute_change(price_result.price.amount, previous_close)

        return QuoteTick(
            symbol=symbol,
            price=str(price_result.price.amount),
            open=str(bar.open.amount) if bar is not None else None,
            high=str(bar.high.amount) if bar is not None else None,
            low=str(bar.low.amount) if bar is not None else None,
            volume=bar.volume if bar is not None else None,
            previous_close=str(previous_close) if previous_close is not None else None,
            change=change,
            change_pct=change_pct,
            is_stale_fallback=price_result.is_stale_fallback,
        )


def _tick_to_payload(tick: QuoteTick) -> dict[str, object]:
    return {
        "symbol": tick.symbol,
        "price": tick.price,
        "open": tick.open,
        "high": tick.high,
        "low": tick.low,
        "volume": tick.volume,
        "previous_close": tick.previous_close,
        "change": tick.change,
        "change_pct": tick.change_pct,
        "is_stale_fallback": tick.is_stale_fallback,
    }
