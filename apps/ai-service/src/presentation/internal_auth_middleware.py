"""internal_auth_middleware.py — Phase 8's code-level enforcement of "AI
Service must never be directly exposed."

Docker Compose network topology (infra/docker-compose.yml) already makes
ai-service unreachable from outside the compose network in most real
deployments, but that is a *deployment convention*, not something this
codebase can verify or test — it is silently defeated by any misconfigured
port mapping, ingress rule, or a developer's local ai-service instance
bound to 0.0.0.0. This middleware makes the boundary an enforced,
testable property of the code itself: every request to a path starting
with `/api/v1/ml` (Phase 7's entire ML surface) must carry a
`X-Internal-Service-Token` header matching `settings.internal_service_token`,
or it is rejected with 403 before reaching any router. `/health`, `/ready`,
and `/api/v1/ml/metrics` are exempted (see rationale below).

This is a shared-secret pattern, not a substitute for mTLS/service-mesh
identity in a real production deployment — disclosed as a scoped, code-
level defense-in-depth measure in docs/phase-8/known-issues.md, not a
claim that this alone is sufficient perimeter security in every possible
deployment topology.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings

_PROTECTED_PREFIX = "/api/v1/ml"
_EXEMPT_PATHS = frozenset({"/api/v1/ml/metrics"})
_TOKEN_HEADER = "x-internal-service-token"


class InternalServiceAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if path.startswith(_PROTECTED_PREFIX) and path not in _EXEMPT_PATHS:
            settings = get_settings()
            presented = request.headers.get(_TOKEN_HEADER)
            if presented is None or presented != settings.internal_service_token:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "success": False,
                        "error": {
                            "code": "DIRECT_ACCESS_FORBIDDEN",
                            "message": (
                                "This endpoint is only reachable through core-api's "
                                "AI proxy — direct access to ai-service is not permitted."
                            ),
                        },
                    },
                )
        return await call_next(request)
