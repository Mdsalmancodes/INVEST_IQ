"""Health and readiness endpoints for ai-service.

Same contract as core-api (Document 5 §14.4): /health is a pure liveness
check (never touches dependencies), /ready checks actual dependency
connectivity. ai-service's Phase 1 dependency surface is Redis only
(redis-cache + redis-broker) — Mongo connectivity is added to this check
when the Mongo-backed feature_snapshots/prediction_runs collections are
actually introduced in Phase 7, not stubbed in now with nothing behind it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from src.infrastructure.cache.redis_clients import RedisClients, get_redis_clients

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyChecks(BaseModel):
    redis_cache: Literal["ok", "error"]
    redis_broker: Literal["ok", "error"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: ReadyChecks


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    response: Response,
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> ReadyResponse:
    checks = ReadyChecks(
        redis_cache=await _check_redis(redis_clients.cache),
        redis_broker=await _check_redis(redis_clients.broker),
    )
    all_ok = all(value == "ok" for value in checks.model_dump().values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ready" if all_ok else "not_ready", checks=checks)


async def _check_redis(client: object) -> Literal["ok", "error"]:
    try:
        await client.ping()  # type: ignore[attr-defined]
        return "ok"
    except Exception:  # noqa: BLE001 — readiness check must never raise
        return "error"
