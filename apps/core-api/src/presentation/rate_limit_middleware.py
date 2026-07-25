"""RateLimitMiddleware — general-purpose, per-request rate limiting for
every route (Phase 8), distinct from LoginRateLimiter (Document 6 §15.2's
login-attempt-specific 5/10-threshold backoff/lock policy, which continues
to apply independently on top of this general limiter for /login
specifically — this middleware does not replace it).

Uses a fixed-window Redis INCR+EXPIRE counter (same well-understood
pattern LoginRateLimiter already established), keyed by:
  - the authenticated user's id, when a valid bearer token is present
    (rate-limits a user's activity regardless of which IP they connect
    from — the correct behavior for API abuse, not just brute-force
    login guessing), else
  - the client's IP address (the only identity available for
    unauthenticated requests, e.g. /register, /login itself).

A stricter, separately-configured window applies specifically to the AI
proxy's model train/retrain endpoints (settings.rate_limit_ai_training_*)
— real model fitting is expensive; the standard window would let a single
user queue up far more concurrent training jobs than is reasonable.

Reuses redis-session (Document 3 §7.7: "sessions/rate-limit counters")
via the EXISTING get_redis_clients().session client — never a new Redis
instance, matching TokenBlacklist/LoginRateLimiter's established pattern.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import Settings, get_settings
from src.domain.auth.exceptions import InvalidTokenError, TokenExpiredError
from src.infrastructure.persistence.redis.clients import get_redis_clients
from src.infrastructure.security.jwt_provider import JwtProvider

_RATE_LIMIT_KEY_PREFIX = "ratelimit:general:"
_AI_TRAINING_PATHS = frozenset({"/api/v1/ai/models/train", "/api/v1/ai/models/retrain"})
_EXEMPT_PATHS = frozenset({"/health", "/ready"})


def _build_jwt_provider(settings: Settings) -> JwtProvider:
    return JwtProvider(
        current_kid=settings.jwt_kid,
        current_secret=settings.jwt_secret.get_secret_value(),
        access_token_ttl_minutes=settings.jwt_access_token_ttl_minutes,
        previous_kid=settings.jwt_previous_kid,
        previous_secret=(
            settings.jwt_previous_secret.get_secret_value()
            if settings.jwt_previous_secret is not None
            else None
        ),
    )


def _resolve_identity(request: Request, settings: Settings) -> str:
    """Prefers the authenticated user's id (rate-limits by identity, not
    just network address); falls back to client IP for unauthenticated
    requests. Deliberately does its own lightweight, best-effort JWT
    parse rather than depending on get_current_user — middleware runs
    before FastAPI's dependency-injection resolution, and this identity
    resolution must never itself reject a request (an invalid/missing
    token here just means "rate-limit by IP instead", not a 401 — that
    remains get_current_user's job, applied later in the request
    lifecycle by whichever route actually requires authentication)."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        raw_token = auth_header[len("Bearer ") :]
        try:
            claims = _build_jwt_provider(settings).verify_access_token(raw_token)
            return f"user:{claims.user_id}"
        except (InvalidTokenError, TokenExpiredError):
            pass
    client_ip = request.client.host if request.client is not None else "unknown"
    return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        settings = get_settings()
        redis: Redis = get_redis_clients().session

        path = request.url.path
        is_ai_training = path in _AI_TRAINING_PATHS
        limit = (
            settings.rate_limit_ai_training_requests_per_window
            if is_ai_training
            else settings.rate_limit_requests_per_window
        )
        window_seconds = (
            settings.rate_limit_ai_training_window_seconds
            if is_ai_training
            else settings.rate_limit_window_seconds
        )

        identity = _resolve_identity(request, settings)
        key = f"{_RATE_LIMIT_KEY_PREFIX}{'ai_training:' if is_ai_training else ''}{identity}"

        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
        except RedisError:
            # Fail OPEN, not closed: a rate limiter is a defense-in-depth
            # measure, not a correctness-critical dependency — if Redis
            # itself is unreachable (an outage, a network blip, or this
            # environment simply not running Redis in this dev/test
            # session), the API must keep serving requests rather than
            # becoming entirely unavailable because a secondary control
            # went down. This mirrors LoginRateLimiter's own established
            # posture (a login-rate-limit outage should not itself
            # constitute a denial-of-service against every login attempt).
            return await call_next(request)

        if count > limit:
            retry_after = await redis.ttl(key)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "success": False,
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please try again later.",
                    },
                },
                headers={"Retry-After": str(max(retry_after, 0))},
            )

        return await call_next(request)
