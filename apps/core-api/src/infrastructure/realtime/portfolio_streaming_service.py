"""PortfolioStreamingService — Phase 9's "Live Portfolio" requirement:
portfolio value, today's P/L, overall P/L, sector allocation, investment
distribution, continuously updated without a page refresh.

Reuses the EXISTING PortfolioCalculationService (Phase 3, unmodified) for
every metric except sector allocation/investment distribution, which is
computed by the NEW sector_allocation.py helper layered on top of
PortfolioCalculationService's own output (see that module's docstring
for why it is not a modification to Phase 3's frozen calculation logic).

Mirrors WatchlistStreamingService's (task 4) exact shape: start()/stop(),
session_scope + dependency_factory for testability,
ConnectionManager.user_ids_subscribed_to() reused as-is (already does
prefix matching) for the "portfolio:" topic prefix — a client subscribes
to "portfolio:<id>" per portfolio it has open, not a single flat
"portfolio" topic, since a user may have multiple portfolios and only
some may be currently visible in the UI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from decimal import Decimal

from observability import get_logger

from src.application.portfolio.calculation_service import (
    PortfolioCalculationService,
    PortfolioSummary,
)
from src.domain.market_data.repositories import InstrumentRepository
from src.domain.portfolio.repositories import PortfolioListFilter, PortfolioRepository
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker
from src.infrastructure.realtime.sector_allocation import (
    SectorAllocationEntry,
    compute_sector_allocation,
)

logger = get_logger(__name__)

_PORTFOLIO_TOPIC_PREFIX = "portfolio:"
_MAX_PORTFOLIOS_PER_USER_PER_TICK = 50
"""Same rationale as WatchlistStreamingService's per-user ceiling (task
4) — bounds one user's tick cost; not a realistic constraint for this
phase's users."""


def _decimal_str(value: Decimal) -> str:
    return str(value)


@dataclass(frozen=True, slots=True)
class PortfolioStreamingDependencies:
    """Bundles the per-tick, per-session dependencies this service
    needs — constructed fresh per tick from a fresh session, matching
    every other Phase 9 streaming service's testability pattern."""

    portfolio_repository: PortfolioRepository
    instrument_repository: InstrumentRepository
    calculation_service: PortfolioCalculationService


DependencyFactory = Callable[[object], PortfolioStreamingDependencies]


class PortfolioStreamingService:
    def __init__(
        self,
        connection_manager: ConnectionManager,
        redis_broker: RedisBroker,
        session_scope: Callable[[], AbstractAsyncContextManager[object]],
        dependency_factory: DependencyFactory,
        poll_interval_seconds: float,
    ) -> None:
        self._connection_manager = connection_manager
        self._redis_broker = redis_broker
        self._session_scope = session_scope
        self._dependency_factory = dependency_factory
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
                # never kill the whole streaming loop.
                logger.warning("realtime.portfolio.tick_failed", error=str(exc))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)

    async def tick(self) -> None:
        """Runs exactly one poll cycle — public so tests can invoke a
        single tick deterministically."""
        user_ids = self._connection_manager.user_ids_subscribed_to(_PORTFOLIO_TOPIC_PREFIX)
        if not user_ids:
            return

        async with self._session_scope() as session:
            deps = self._dependency_factory(session)
            for user_id in user_ids:
                await self._publish_for_user(user_id, deps)

    async def _publish_for_user(self, user_id: str, deps: PortfolioStreamingDependencies) -> None:
        try:
            page = await deps.portfolio_repository.list_for_user(
                user_id, PortfolioListFilter(page=1, page_size=_MAX_PORTFOLIOS_PER_USER_PER_TICK)
            )
        except Exception as exc:  # noqa: BLE001 - isolate one user's
            # failure from every other subscribed user's tick this cycle.
            logger.warning("realtime.portfolio.list_failed", user_id=user_id, error=str(exc))
            return

        for portfolio in page.items:
            try:
                summary = await deps.calculation_service.compute_summary(portfolio)
                sector_allocation = await compute_sector_allocation(
                    summary, deps.instrument_repository
                )
            except Exception as exc:  # noqa: BLE001 - isolate one
                # portfolio's failure from the user's other portfolios.
                logger.warning(
                    "realtime.portfolio.compute_failed",
                    user_id=user_id,
                    portfolio_id=str(portfolio.id),
                    error=str(exc),
                )
                continue
            await self._redis_broker.publish(
                channels.portfolio_channel(user_id, str(portfolio.id)),
                _summary_to_payload(summary, sector_allocation),
            )


def _summary_to_payload(
    summary: PortfolioSummary, sector_allocation: tuple[SectorAllocationEntry, ...]
) -> dict[str, object]:
    return {
        "portfolio_id": summary.portfolio_id,
        "total_investment": _decimal_str(summary.total_investment.amount),
        "current_value": _decimal_str(summary.current_value.amount),
        "profit_loss": _decimal_str(summary.profit_loss.amount),
        "profit_loss_pct": _decimal_str(summary.profit_loss_pct),
        "realized_gain": _decimal_str(summary.realized_gain.amount),
        "unrealized_gain": _decimal_str(summary.unrealized_gain.amount),
        "dividend_income": _decimal_str(summary.dividend_income.amount),
        "daily_gain": _decimal_str(summary.daily_gain.amount),
        "sector_allocation": [
            {
                "sector": entry.sector,
                "market_value": _decimal_str(entry.market_value.amount),
                "allocation_pct": _decimal_str(entry.allocation_pct),
            }
            for entry in sector_allocation
        ],
    }
