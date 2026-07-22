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

from src.config import get_settings
from src.presentation.routers.auth_router import router as auth_router
from src.presentation.routers.health_router import router as health_router
from src.presentation.routers.market_data_router import router as market_data_router
from src.presentation.routers.portfolio_router import router as portfolio_router
from src.presentation.routers.watchlist_router import router as watchlist_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)
    logger.info("service.startup", environment=settings.environment)
    yield
    logger.info("service.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="INVEST IQ — core-api",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(portfolio_router)
    app.include_router(market_data_router)
    app.include_router(watchlist_router)

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
