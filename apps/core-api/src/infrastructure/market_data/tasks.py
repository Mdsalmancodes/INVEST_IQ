"""sync_instrument_bars — the Celery task implementing Document 5 §11.2's
ingestion pipeline (Fetch -> Validate & Dedupe -> Normalize -> Persist)
for a single instrument's daily bars.

Per Document 5 §11.2 stage 5 (Publish Event) and the Mongo raw-snapshot
persistence in stage 4: NOT built in this phase — no Mongo instance exists
anywhere in this codebase, and no Redis Pub/Sub consumer exists yet either
(both are genuinely out of the founder's explicit Phase 4 requirement
list: "Background Sync" was requested as a capability — keeping OHLCV
data fresh — not the full 5-stage pipeline including downstream event
consumers this phase has nothing to consume them). This is a disclosed
simplification, not a silent one.

Celery tasks are synchronous by contract; the use cases this task drives
are async (matching the rest of the codebase's async-everywhere
convention, Document 7 §19.4) — asyncio.run() bridges the two per task
invocation, which is the standard, documented pattern for this
combination (a new event loop per task run, not a long-lived loop shared
across tasks, since Celery's worker model runs tasks in separate
processes/threads, not as coroutines on a shared loop).

The pipeline logic itself (`run_sync_pipeline`) takes its dependencies as
parameters rather than constructing them internally — this is what makes
it unit-testable with fakes without a real Postgres/network connection;
only the thin `sync_instrument_bars` Celery task wrapper does the real
wiring (session factory, provider router construction).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from observability import get_logger

from src.application.market_data.provider_router import ProviderRouter
from src.application.market_data.validation_service import MarketDataValidationService
from src.domain.market_data.entities import OhlcvBar
from src.domain.market_data.repositories import InstrumentRepository, OhlcvBarRepository
from src.domain.market_data.value_objects import Interval
from src.infrastructure.market_data.celery_app import celery_app
from src.infrastructure.market_data.providers.yfinance_provider import YFinanceProvider
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
)
from src.infrastructure.persistence.postgres.session import get_session_factory

logger = get_logger(__name__)

_BACKFILL_LOOKBACK_DAYS = 7  # daily sync window - re-fetches the last week
# to naturally self-heal any single missed run, without re-fetching full
# history every time (Document 5 §11.3's backfill job is the separate,
# heavier one-time operation for genuinely new symbols — this task is the
# ongoing "keep recent data fresh" sync, a distinct concern).


async def run_sync_pipeline(
    symbol: str,
    instrument_repository: InstrumentRepository,
    ohlcv_bar_repository: OhlcvBarRepository,
    provider_router: ProviderRouter,
    validation_service: MarketDataValidationService,
    lookback_days: int = _BACKFILL_LOOKBACK_DAYS,
) -> int:
    """The actual ingestion pipeline logic — Fetch -> Validate & Dedupe ->
    Normalize -> Persist (Document 5 §11.2). Returns the count of bars
    actually persisted (post-validation). Takes all dependencies as
    parameters (see module docstring) so it's directly unit-testable.
    """
    instrument = await instrument_repository.get_by_symbol(symbol)
    if instrument is None:
        logger.warning("market_data.sync.instrument_not_found", symbol=symbol)
        return 0

    end = date.today()
    start = end - timedelta(days=lookback_days)

    try:
        raw_bars = await provider_router.resolve_bars(symbol, Interval.ONE_DAY, start, end)
    except Exception as exc:  # noqa: BLE001 - log and skip this symbol,
        # never crash the whole sync run over one symbol's failure.
        logger.error("market_data.sync.fetch_failed", symbol=symbol, error=str(exc))
        return 0

    valid_bars = tuple(bar for bar in raw_bars if validation_service.validate_bar(bar).is_valid)
    deduped_bars = validation_service.dedupe_bars(valid_bars)

    domain_bars = tuple(
        OhlcvBar(
            instrument_id=instrument.id,
            interval=bar.interval,
            bar_time=bar.bar_time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            adjusted_close=bar.close,
            volume=bar.volume,
            is_closed=bar.is_closed,
            source=bar.source,
            created_at=bar.bar_time,
        )
        for bar in deduped_bars
    )
    if domain_bars:
        await ohlcv_bar_repository.save_many(domain_bars)

    logger.info(
        "market_data.sync.completed",
        symbol=symbol,
        fetched=len(raw_bars),
        persisted=len(domain_bars),
    )
    return len(domain_bars)


async def _sync_instrument_bars_async(symbol: str) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        instrument_repository = SqlAlchemyInstrumentRepository(session)
        ohlcv_bar_repository = SqlAlchemyOhlcvBarRepository(session)
        validation_service = MarketDataValidationService()

        # Production deployments would configure ProviderRouter with a
        # paid real-time/delayed provider first, yfinance last (or not at
        # all — Document 5 §11.1 marks it dev-only) — this task's router
        # construction is intentionally the same one used for local/dev
        # runs of this phase, since no paid provider credentials exist in
        # this environment (disclosed limitation, same as
        # AlphaVantageProvider's get_bars()).
        router = ProviderRouter(
            quote_providers=(YFinanceProvider(),),
            historical_providers=(YFinanceProvider(),),
        )

        count = await run_sync_pipeline(
            symbol, instrument_repository, ohlcv_bar_repository, router, validation_service
        )
        await session.commit()
        return count


@celery_app.task(name="market_data.sync_instrument_bars")  # type: ignore[untyped-decorator]
# `[untyped-decorator]` here: celery's @app.task decorator is itself
# untyped (no py.typed marker, per the mypy override above) — even with
# ignore_missing_imports, mypy can't infer the decorator's return type,
# so it flags this function as "untyped" despite the explicit `-> int`
# annotation below. A real third-party stub gap, not a defect in this
# function's own signature.
def sync_instrument_bars(symbol: str) -> int:
    return asyncio.run(_sync_instrument_bars_async(symbol))
