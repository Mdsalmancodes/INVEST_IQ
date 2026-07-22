"""Health and readiness endpoints.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md §14.4,
every service implements this contract identically:

    GET /health -> 200 {"status": "ok"}                          (liveness)
    GET /ready  -> 200 {"status": "ready", "checks": {...}}       (readiness)

/health never touches the database or Redis — it only answers "is the process
up," so a slow dependency never causes a liveness-probe restart loop.
/ready actually checks dependencies, since it answers "can this instance
serve traffic right now."
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.postgres.session import get_db_session
from src.infrastructure.persistence.redis.clients import RedisClients, get_redis_clients

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyChecks(BaseModel):
    db: Literal["ok", "error"]
    redis_cache: Literal["ok", "error"]
    redis_broker: Literal["ok", "error"]
    redis_session: Literal["ok", "error"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: ReadyChecks


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> ReadyResponse:
    checks = ReadyChecks(
        db=await _check_db(db),
        redis_cache=await _check_redis(redis_clients.cache),
        redis_broker=await _check_redis(redis_clients.broker),
        redis_session=await _check_redis(redis_clients.session),
    )
    all_ok = all(value == "ok" for value in checks.model_dump().values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ready" if all_ok else "not_ready", checks=checks)


async def _check_db(db: AsyncSession) -> Literal["ok", "error"]:
    try:
        await db.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 — readiness check must never raise
        return "error"


async def _check_redis(client: object) -> Literal["ok", "error"]:
    try:
        await client.ping()  # type: ignore[attr-defined]
        return "ok"
    except Exception:  # noqa: BLE001 — readiness check must never raise
        return "error"
