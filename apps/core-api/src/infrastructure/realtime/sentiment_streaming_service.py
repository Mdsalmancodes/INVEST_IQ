"""SentimentStreamingService — Phase 9's "Live Sentiment" requirement:
continuously refresh the sentiment dashboard without a page reload.

DISCLOSED DESIGN DECISION (important — read before assuming this calls
ai-service's dedicated sentiment endpoint): this service does NOT call
AiServiceClient.analyze_sentiment(). That endpoint's request contract
(ai-service's SentimentAnalysisRequest, `texts: list[str]` with
`min_length=1`) REQUIRES actual financial-news/company-news/social-
media/Reddit text content to analyze — and no live news/Reddit
ingestion pipeline exists anywhere in this codebase (confirmed via a
search before writing this service; Phase 7's own known-issues.md
already disclosed this exact gap for the on-demand SentimentDashboard
UI, which only ever analyzes text a user manually pastes in). A
streaming service has no such live text feed to poll, so calling
analyze_sentiment on a timer with no real new text each tick would mean
either (a) re-analyzing the same stale/empty text repeatedly (dishonest
"live" behavior dressed up to look real), or (b) fabricating placeholder
text (actively misleading — presenting made-up data as a real sentiment
signal).

Instead, this service reuses AiServiceClient.get_recommendation()'s
EXISTING `sentiment_score` field (RecommendationResponse.sentiment_score,
ai-service's ml_dto.py — a real, already-computed value: the Decision
Engine's own market_sentiment_score, part of its normal prediction
output, not fabricated for this task) — the one genuinely live sentiment
signal this codebase has an actual data path for. This is the SAME
underlying HTTP call AiPredictionStreamingService (task 6) already
makes each tick for "ai:SYMBOL" topics; this service makes its own
independent call for "sentiment:SYMBOL" topics (a client may subscribe
to one without the other — e.g. a sentiment-only dashboard widget), and
publishes only the sentiment-relevant slice of the response.

This is disclosed explicitly here and in docs/phase-9/known-issues.md as
a genuine, honest gap this task does not close (a true live news/Reddit
ingestion pipeline remains unbuilt, same category as Phase 7's own
disclosed limitation) — this service delivers "the sentiment dashboard
auto-refreshes" using the real signal that exists, rather than building
something that only looks like it analyzes live text.
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


def _sentiment_symbols_from_topics(topics: frozenset[str]) -> frozenset[str]:
    return frozenset(
        topic.removeprefix("sentiment:") for topic in topics if topic.startswith("sentiment:")
    )


class SentimentStreamingService:
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
                logger.warning("realtime.sentiment.tick_failed", error=str(exc))
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_seconds)

    async def tick(self) -> None:
        """Runs exactly one poll cycle — public so tests can invoke a
        single tick deterministically."""
        symbols = _sentiment_symbols_from_topics(self._connection_manager.all_subscribed_topics())
        for symbol in symbols:
            await self._publish_for_symbol(symbol)

    async def _publish_for_symbol(self, symbol: str) -> None:
        try:
            response = await self._ai_service_client.get_recommendation(symbol)
        except Exception as exc:  # noqa: BLE001 - isolate one symbol's
            # failure from every other subscribed symbol's tick this cycle.
            logger.warning("realtime.sentiment.fetch_failed", symbol=symbol, error=str(exc))
            return

        if response.status_code != 200:
            logger.info(
                "realtime.sentiment.unavailable", symbol=symbol, status_code=response.status_code
            )
            return

        sentiment_score = response.body.get("sentiment_score")
        if sentiment_score is None:
            # A well-formed 200 response should always carry this field
            # (it's non-optional in ai-service's own RecommendationResponse
            # schema) — a missing field here would indicate a genuine
            # contract mismatch, not a normal "not ready yet" case, so
            # this is logged as a warning rather than silently skipped
            # like the non-200 case above.
            logger.warning("realtime.sentiment.missing_field", symbol=symbol)
            return

        await self._redis_broker.publish(
            channels.sentiment_channel(symbol),
            {"symbol": symbol, "sentiment_score": sentiment_score},
        )
