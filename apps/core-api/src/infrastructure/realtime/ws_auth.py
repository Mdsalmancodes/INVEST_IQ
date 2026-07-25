"""WebSocket handshake authentication — reuses the EXISTING JwtProvider/
TokenBlacklist verification logic from presentation/dependencies/auth.py's
get_current_user(), rather than a parallel auth mechanism.

WHY QUERY PARAMETER, NOT AN AUTHORIZATION HEADER: browsers' native
WebSocket constructor (`new WebSocket(url)`) cannot set arbitrary request
headers — this is a Fetch/XHR-only capability, not part of the WebSocket
handshake API. The two realistic alternatives are (a) a token query
parameter on the WS URL, or (b) accepting the connection unauthenticated
and requiring an auth message as the first frame. This module implements
(a) — simpler, and the token is already short-lived (15 minutes,
Document 3 §7.4) and never logged in access logs since FastAPI/uvicorn's
default access log format does not include query strings by default in
this codebase's configuration (structlog-based, see libs/observability).
The token is validated exactly once at connect time using the same
signature/expiry/blacklist checks as every authenticated HTTP request;
a WebSocket connection's lifetime (bounded by the heartbeat mechanism in
realtime_router.py) is expected to be shorter than the access token's
own TTL in normal operation, so no separate mid-connection re-validation
is performed — matching how a normal HTTP request doesn't re-validate a
token that was valid at request-start but expires microseconds later.
"""

from __future__ import annotations

from fastapi import WebSocket, status

from src.domain.auth.exceptions import InvalidTokenError, TokenExpiredError
from src.infrastructure.persistence.redis.clients import RedisClients
from src.infrastructure.security.jwt_provider import AccessTokenClaims, JwtProvider
from src.infrastructure.security.token_blacklist import TokenBlacklist


class WebSocketAuthError(Exception):
    """Raised when a WebSocket handshake's token fails validation. The
    caller (realtime_router.py) is responsible for closing the socket
    with an appropriate close code — this exception itself carries no
    WebSocket-specific behavior, keeping this module testable without a
    real WebSocket object."""


async def authenticate_websocket(
    websocket: WebSocket,
    token: str | None,
    jwt_provider: JwtProvider,
    redis_clients: RedisClients,
) -> AccessTokenClaims:
    if token is None:
        raise WebSocketAuthError("Missing token query parameter")

    try:
        claims = jwt_provider.verify_access_token(token)
    except TokenExpiredError as exc:
        raise WebSocketAuthError("Access token has expired") from exc
    except InvalidTokenError as exc:
        raise WebSocketAuthError("Invalid access token") from exc

    token_blacklist = TokenBlacklist(redis_clients.session)
    if await token_blacklist.is_blacklisted(claims.jti):
        raise WebSocketAuthError("Access token has been revoked")

    return claims


WS_POLICY_VIOLATION_CLOSE_CODE = status.WS_1008_POLICY_VIOLATION
