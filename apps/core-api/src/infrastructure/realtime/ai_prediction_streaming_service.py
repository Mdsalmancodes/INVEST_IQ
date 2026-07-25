"""AiPredictionStreamingService — Phase 9's "Live AI" requirement:
whenever market data changes, automatically re-run the prediction
pipeline (LSTM/ARIMA/Prophet/RandomForest/XGBoost via ai-service's
Decision Engine) and push updated Buy/Sell/Hold recommendations.

CROSS-SERVICE BOUNDARY (different from tasks 3-5): this is the first
Phase 9 streaming service that needs data from ai-service, not just
core-api's own database. Per Phase 8's "AI Service must never be
directly exposed" architecture, this service NEVER calls ai-service
directly — it goes through the EXISTING AiServiceClient Protocol
(application/ai_proxy/ai_service_client.py) exactly as ai_proxy_router.py
already does for the HTTP-triggered case. core-api never calls
individual models (LSTM, ARIMA, etc.) itself; get_recommendation()
already proxies to ai-service's Decision Engine, which is the sole
orchestration point for the ensemble — this streaming service adds a
NEW trigger path (a timer) to an EXISTING capability, not a new
capability.

TRIGGER CONDITION — "whenever market data changes": interpreted as
re-running on this service's own independent polling interval
(settings.realtime_ai_poll_interval_seconds, deliberately much longer
than every other Phase 9 streaming loop — a full ensemble prediction is
expensive), rather than literally diffing every individual price tick
server-side to detect "change." A polling loop already achieves the
same practical outcome (predictions refresh regularly while the market
moves) without the added complexity of change-detection logic whose
only purpose would be deciding when to do exactly what this loop
already does on a fixed cadence. Disclosed here and in
docs/phase-9/known-issues.md, not silently implied to be a literal
per-tick diff.

No database session is needed at all (AiServiceClient's get_recommendation
makes its own HTTP call to ai-service; ai-service's own Decision Engine
fetches whatever market data it needs via its already-existing HTTP
MarketDataRepository, Phase 7, unmodified) — this service is simpler in
shape than tasks 3-5's, with no session_scope/dependency_factory
indirection needed.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from observability import get_logger

from src.application.ai_proxy.ai_service_client import AiServiceClient
from src.infrastructure.realtime import channels
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker

logger = get_logger(__name__)


def _ai_symbols_from_topics(topics: frozenset[str]) -> frozenset[str]:
    return frozenset(topic.removeprefix("ai:") for topic in topics if topic.startswith("ai:"))


class AiPredictionStreamingService:
    def __init__(
        self,
        connection_manager: ConnectionManager,
        redis_broker: RedisBroker,
        ai_service_client: AiServiceClient,
        poll_interval_seconds: float,
    ) -> None:
        self._connection_manager = connection_manager
        self._redis_broker = redis_broker
        self._ai_service_client = ai_service_client
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
                logger.warning("realtime.ai.tick_failed", error=str(exc))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)

    async def tick(self) -> None:
        """Runs exactly one poll cycle — public so tests can invoke a
        single tick deterministically."""
        symbols = _ai_symbols_from_topics(self._connection_manager.all_subscribed_topics())
        for symbol in symbols:
            await self._publish_for_symbol(symbol)

    async def _publish_for_symbol(self, symbol: str) -> None:
        try:
            response = await self._ai_service_client.get_recommendation(symbol)
        except Exception as exc:  # noqa: BLE001 - isolate one symbol's
            # failure (ai-service unreachable, insufficient data, etc.)
            # from every other subscribed symbol's tick this cycle.
            logger.warning("realtime.ai.recommendation_failed", symbol=symbol, error=str(exc))
            return

        if response.status_code != 200:
            # A non-200 (e.g. 422 insufficient data, matching
            # ai_proxy_router.py's own pass-through-status-code
            # convention) is not a transport failure — it's a valid,
            # meaningful "no recommendation available yet" response for
            # this symbol; log at a lower severity and skip publishing
            # rather than treating it as an error.
            logger.info(
                "realtime.ai.recommendation_unavailable",
                symbol=symbol,
                status_code=response.status_code,
            )
            return

        await self._redis_broker.publish(channels.ai_prediction_channel(symbol), response.body)
