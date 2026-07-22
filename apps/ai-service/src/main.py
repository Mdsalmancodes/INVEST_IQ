"""ai-service application factory — infrastructure skeleton only (Phase 1).

Per docs/architecture/02-clean-architecture-folder-frontend.md §5.3: app
factory + router registration only, no business logic here. FastAPI's own
dependency injection (Depends) is used for Redis clients and settings —
no custom DI container, per the "use FastAPI dependency injection" directive.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from observability import configure_logging, get_logger

from src.config import get_settings
from src.presentation.routers.health_router import router as health_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(service_name=settings.service_name, level=settings.log_level)
    logger.info("service.startup", environment=settings.environment)
    yield
    logger.info("service.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="INVEST IQ — ai-service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app


app = create_app()
