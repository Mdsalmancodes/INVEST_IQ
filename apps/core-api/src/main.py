"""core-api application factory.

Per docs/architecture/02-clean-architecture-folder-frontend.md §5.3:
main.py is the FastAPI app factory and router registration point only —
business logic lives in application/domain, never here.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from observability import configure_logging, get_logger

from src.application.market_data.get_current_price_use_case import GetCurrentPriceUseCase
from src.application.market_data.get_market_status_use_case import GetMarketStatusUseCase
from src.application.portfolio.calculation_service import PortfolioCalculationService
from src.application.watchlist.enrichment_service import WatchlistEnrichmentService
from src.config import get_settings
from src.infrastructure.http.ai_service_http_client import get_ai_service_http_client
from src.infrastructure.market_data.cache import MarketDataCache
from src.infrastructure.market_data.real_price_provider import RealPriceProvider
from src.infrastructure.persistence.postgres.repositories.alert_repository import (
    SqlAlchemyAlertRepository,
)
from src.infrastructure.persistence.postgres.repositories.instrument_repository import (
    SqlAlchemyInstrumentRepository,
)
from src.infrastructure.persistence.postgres.repositories.notification_repository import (
    SqlAlchemyNotificationRepository,
)
from src.infrastructure.persistence.postgres.repositories.ohlcv_bar_repository import (
    SqlAlchemyOhlcvBarRepository,
)
from src.infrastructure.persistence.postgres.repositories.portfolio_repository import (
    SqlAlchemyPortfolioRepository,
)
from src.infrastructure.persistence.postgres.repositories.transaction_repository import (
    SqlAlchemyTransactionRepository,
)
from src.infrastructure.persistence.postgres.repositories.watchlist_repository import (
    SqlAlchemyWatchlistRepository,
)
from src.infrastructure.persistence.postgres.session import get_committing_session_scope
from src.infrastructure.persistence.redis.clients import get_redis_clients
from src.infrastructure.realtime.ai_prediction_streaming_service import (
    AiPredictionStreamingService,
)
from src.infrastructure.realtime.alert_evaluation_streaming_service import (
    AlertEvaluationDependencies,
    AlertEvaluationStreamingService,
)
from src.infrastructure.realtime.market_data_streaming_service import MarketDataStreamingService
from src.infrastructure.realtime.portfolio_streaming_service import (
    PortfolioStreamingDependencies,
    PortfolioStreamingService,
)
from src.infrastructure.realtime.realtime_service import RealtimeService
from src.infrastructure.realtime.redis_broker import RedisBroker
from src.infrastructure.realtime.sentiment_streaming_service import SentimentStreamingService
from src.infrastructure.realtime.watchlist_streaming_service import (
    WatchlistStreamingDependencies,
    WatchlistStreamingService,
)
from src.presentation.dependencies.ai_proxy_use_cases import get_ai_service_client
from src.presentation.dependencies.market_data_use_cases import get_provider_router
from src.presentation.dependencies.realtime import get_connection_manager
from src.presentation.rate_limit_middleware import RateLimitMiddleware
from src.presentation.routers.ai_proxy_router import router as ai_proxy_router
from src.presentation.routers.alert_router import router as alert_router
from src.presentation.routers.auth_router import router as auth_router
from src.presentation.routers.health_router import router as health_router
from src.presentation.routers.market_data_router import router as market_data_router
from src.presentation.routers.notification_router import router as notification_router
from src.presentation.routers.portfolio_router import router as portfolio_router
from src.presentation.routers.realtime_router import router as realtime_router
from src.presentation.routers.watchlist_router import router as watchlist_router
from src.presentation.security_headers_middleware import SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)
    logger.info("service.startup", environment=settings.environment)

    # Phase 9 — Real-Time Market Intelligence. One RealtimeService per
    # process: subscribes (via Redis Pub/Sub pattern-subscribe) to every
    # realtime:* channel any publisher in this or ANY other core-api
    # instance writes to, and fans matching messages out to this
    # process's own locally-connected WebSocket clients via
    # ConnectionManager — see realtime_service.py's module docstring for
    # the full horizontal-scalability rationale.
    realtime_service = RealtimeService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
    )
    realtime_service.start()

    # Phase 9 — "Live Stock Data." Polls (at
    # settings.realtime_market_data_poll_interval_seconds) every symbol
    # any connected client has subscribed to, publishing each tick to
    # Redis so RealtimeService (any instance) fans it out — see that
    # module's own docstring for why this is a polling loop rather than a
    # Celery task or a genuinely continuous streaming feed.
    market_data_streaming_service = MarketDataStreamingService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
        session_scope=get_committing_session_scope,
        repository_factory=lambda session: (
            SqlAlchemyInstrumentRepository(session),  # type: ignore[arg-type]
            SqlAlchemyOhlcvBarRepository(session),  # type: ignore[arg-type]
        ),
        provider_router=get_provider_router(),
        market_data_cache=MarketDataCache(get_redis_clients().cache),
        market_status_use_case=GetMarketStatusUseCase(),
        poll_interval_seconds=settings.realtime_market_data_poll_interval_seconds,
    )
    market_data_streaming_service.start()

    # Phase 9 — "Live Watchlist." A separate, longer-interval loop
    # (settings.realtime_watchlist_poll_interval_seconds) than raw quote
    # streaming, since per-tick watchlist enrichment is more expensive
    # (N items x a full price lookup each) and doesn't need to feel as
    # instantaneous as the raw ticker — see that module's own docstring.
    def _watchlist_dependency_factory(session: object) -> WatchlistStreamingDependencies:
        instrument_repository = SqlAlchemyInstrumentRepository(session)  # type: ignore[arg-type]
        ohlcv_bar_repository = SqlAlchemyOhlcvBarRepository(session)  # type: ignore[arg-type]
        get_current_price_use_case = GetCurrentPriceUseCase(
            instrument_repository,
            ohlcv_bar_repository,
            get_provider_router(),
            MarketDataCache(get_redis_clients().cache),
        )
        return WatchlistStreamingDependencies(
            watchlist_repository=SqlAlchemyWatchlistRepository(session),  # type: ignore[arg-type]
            enrichment_service=WatchlistEnrichmentService(
                instrument_repository, get_current_price_use_case, GetMarketStatusUseCase()
            ),
        )

    watchlist_streaming_service = WatchlistStreamingService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
        session_scope=get_committing_session_scope,
        dependency_factory=_watchlist_dependency_factory,
        poll_interval_seconds=settings.realtime_watchlist_poll_interval_seconds,
    )
    watchlist_streaming_service.start()

    # Phase 9 — "Live Portfolio." Same shape/rationale as the watchlist
    # streaming loop above — see portfolio_streaming_service.py's own
    # docstring.
    def _portfolio_dependency_factory(session: object) -> PortfolioStreamingDependencies:
        ohlcv_bar_repository = SqlAlchemyOhlcvBarRepository(session)  # type: ignore[arg-type]
        instrument_repository = SqlAlchemyInstrumentRepository(session)  # type: ignore[arg-type]
        return PortfolioStreamingDependencies(
            portfolio_repository=SqlAlchemyPortfolioRepository(session),  # type: ignore[arg-type]
            instrument_repository=instrument_repository,
            calculation_service=PortfolioCalculationService(
                RealPriceProvider(ohlcv_bar_repository),
                SqlAlchemyTransactionRepository(session),  # type: ignore[arg-type]
            ),
        )

    portfolio_streaming_service = PortfolioStreamingService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
        session_scope=get_committing_session_scope,
        dependency_factory=_portfolio_dependency_factory,
        poll_interval_seconds=settings.realtime_portfolio_poll_interval_seconds,
    )
    portfolio_streaming_service.start()

    # Phase 9 — "Live AI." Goes through the EXISTING Phase 8
    # AiServiceClient (mock-vs-live branching reused as-is from
    # get_ai_service_client — never re-derived) — core-api still never
    # calls ai-service directly outside that one sanctioned client, and
    # ai-service itself is still only ever reachable via its Phase 8
    # InternalServiceAuthMiddleware-guarded internal API.
    ai_prediction_streaming_service = AiPredictionStreamingService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
        ai_service_client=get_ai_service_client(settings),
        poll_interval_seconds=settings.realtime_ai_poll_interval_seconds,
    )
    ai_prediction_streaming_service.start()

    # Phase 9 — "Live Sentiment." Shares the same AiServiceClient
    # instance and underlying get_recommendation() call as the AI
    # prediction loop above — see sentiment_streaming_service.py's
    # module docstring for the full disclosed design rationale.
    sentiment_streaming_service = SentimentStreamingService(
        connection_manager=get_connection_manager(),
        redis_broker=RedisBroker(get_redis_clients().broker),
        ai_service_client=get_ai_service_client(settings),
        poll_interval_seconds=settings.realtime_sentiment_poll_interval_seconds,
    )
    sentiment_streaming_service.start()

    # Phase 9 — "Live Alerts" — the Alert Evaluation Engine, closing the
    # standing Phase 6/7/8 known-issue (Alert.can_trigger_now()/trigger()
    # existed but nothing ever called them). Subscribes independently to
    # every "realtime:quote:*" message ANY core-api instance publishes
    # (via MarketDataStreamingService, task 3, completely unmodified) —
    # see alert_evaluation_streaming_service.py's own docstring for why
    # this is an independent Pub/Sub subscription rather than a hook into
    # that already-verified service.
    def _alert_dependency_factory(session: object) -> AlertEvaluationDependencies:
        return AlertEvaluationDependencies(
            alert_repository=SqlAlchemyAlertRepository(session),  # type: ignore[arg-type]
            notification_repository=SqlAlchemyNotificationRepository(session),  # type: ignore[arg-type]
            instrument_repository=SqlAlchemyInstrumentRepository(session),  # type: ignore[arg-type]
            ohlcv_bar_repository=SqlAlchemyOhlcvBarRepository(session),  # type: ignore[arg-type]
        )

    alert_evaluation_streaming_service = AlertEvaluationStreamingService(
        redis_broker=RedisBroker(get_redis_clients().broker),
        session_scope=get_committing_session_scope,
        dependency_factory=_alert_dependency_factory,
    )
    alert_evaluation_streaming_service.start()

    yield

    await alert_evaluation_streaming_service.stop()
    await sentiment_streaming_service.stop()
    await ai_prediction_streaming_service.stop()
    await portfolio_streaming_service.stop()
    await watchlist_streaming_service.stop()

    await market_data_streaming_service.stop()
    await realtime_service.stop()
    # Only close if get_ai_service_http_client() was ever actually called
    # (AI_SERVICE_MODE=live) — calling it here unconditionally would
    # instantiate a brand-new, unused httpx.AsyncClient in mock mode just
    # to immediately close it.
    if get_ai_service_http_client.cache_info().currsize > 0:
        await get_ai_service_http_client().aclose()
    logger.info("service.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    print("CORS ORIGINS =", settings.cors_allowed_origins)

    app = FastAPI(
        title="INVEST IQ — core-api",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        # Phase 8 tightening: an explicit method/header allowlist rather
        # than "*" — the API only ever needs these methods, and only ever
        # reads Content-Type/Authorization from a cross-origin request
        # (Authorization carries the bearer token; Content-Type is
        # required for any JSON request body). allow_credentials=True
        # requires an explicit (non-"*") origin list to be meaningful
        # anyway per the CORS spec, which cors_allowed_origins already is.
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(portfolio_router)
    app.include_router(market_data_router)
    app.include_router(watchlist_router)
    app.include_router(alert_router)
    app.include_router(notification_router)
    app.include_router(ai_proxy_router)
    app.include_router(realtime_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for genuinely unexpected exceptions — Document 5 §14.3:
        "Unhandled/unexpected exceptions: caught by a final catch-all
        handler, logged with full stack trace at ERROR level with
        requestId, returned to the client as a generic INTERNAL_ERROR
        (never leaking stack traces, internal paths, or exception messages
        to the client in production)."

        Domain exceptions never reach this handler — every route that can
        raise one catches it explicitly and calls raise_as_http() (see
        auth_router.py), which raises a proper HTTPException with a
        specific status code before this catch-all would ever see it. This
        handler exists for the class of failure that isn't a business-rule
        violation at all (e.g. the database being unreachable), which is
        exactly the gap that surfaced as a bare "Internal Server Error"
        during this session's HTTP smoke test against a real running
        server with Postgres unavailable — a real, if minor, finding from
        the verify-first workflow, not a hypothetical.
        """
        request_id = str(uuid.uuid4())
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            path=request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                },
                "meta": {"requestId": request_id},
            },
        )

    return app


app = create_app()
