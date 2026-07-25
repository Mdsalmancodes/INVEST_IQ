"""realtime_router.py — the single WebSocket endpoint for Phase 9's
real-time layer.

Endpoint: WS /api/v1/realtime/ws?token=<access_token>

Per-connection protocol (JSON frames both directions):
- Client -> Server: {"action": "subscribe", "topics": [...]}
                     {"action": "unsubscribe", "topics": [...]}
                     {"action": "ping"}
- Server -> Client: {"type": "connected", "userId": "..."}
                     {"type": "pong"}
                     {"type": "quote"|"watchlist"|"portfolio"|"ai"|
                              "sentiment"|"alert"|"ticker", "data": {...}}
                     {"type": "error", "message": "..."}

Topics are the same strings used throughout the frontend to express
subscription intent, deliberately simpler than the internal Redis
channel names (channels.py) — e.g. a client subscribes to
"quote:AAPL", not to knowing this maps to "realtime:quote:AAPL"
server-side. This indirection lets the internal channel-naming scheme
change without ever being a breaking change for a WebSocket client.

HEARTBEAT: the server sends a {"type": "heartbeat"} frame every
HEARTBEAT_INTERVAL_SECONDS. This serves two purposes: (1) it is the
"heartbeat monitoring" the founder explicitly requested, letting the
frontend detect a genuinely stalled-but-not-yet-closed connection if no
heartbeat arrives for too long; (2) periodic traffic on an idle
connection prevents some intermediary proxies/load balancers from
silently timing out a connection that has no application data flowing.
The client is expected to reply with {"action": "ping"} (server replies
{"type": "pong"}) on its own cadence too — see frontend task 11's
useRealtimeConnection hook — giving bidirectional liveness detection
rather than relying on the server's heartbeat alone.

RECONNECTION is fundamentally a CLIENT-side responsibility (there is no
way for a server to "reconnect" a socket the client's browser closed) —
this router's job is only to make reconnecting cheap and safe: accepting
a fresh connection with the same token is always valid (no server-side
session/handshake nonce to invalidate), and a client's re-subscribe
after reconnecting is idempotent (subscribing to an already-subscribed
topic is a no-op, not an error).
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from observability import get_logger

from src.infrastructure.persistence.redis.clients import RedisClients, get_redis_clients
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.subscription_registry import SubscriptionRegistry
from src.infrastructure.realtime.ws_auth import (
    WS_POLICY_VIOLATION_CLOSE_CODE,
    WebSocketAuthError,
    authenticate_websocket,
)
from src.infrastructure.security.jwt_provider import JwtProvider
from src.presentation.dependencies.auth import get_jwt_provider
from src.presentation.dependencies.realtime import get_connection_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])

HEARTBEAT_INTERVAL_SECONDS = 15.0


@router.websocket("/ws")
async def realtime_websocket(
    websocket: WebSocket,
    connection_manager: Annotated[ConnectionManager, Depends(get_connection_manager)],
    jwt_provider: Annotated[JwtProvider, Depends(get_jwt_provider)],
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> None:
    token = websocket.query_params.get("token")

    try:
        claims = await authenticate_websocket(websocket, token, jwt_provider, redis_clients)
    except WebSocketAuthError as exc:
        # The handshake itself (accept()) must happen before a close code
        # with a reason can be sent per the ASGI WebSocket spec used by
        # Starlette/FastAPI — accept-then-immediately-close is the
        # standard pattern for a rejected-but-not-silently-dropped
        # connection, letting the client's onclose handler see the real
        # reason rather than a generic connection-refused error.
        await websocket.accept()
        await websocket.close(code=WS_POLICY_VIOLATION_CLOSE_CODE, reason=str(exc))
        logger.warning("realtime.auth_rejected", reason=str(exc))
        return

    user_id = str(claims.user_id)

    subscriptions = await connection_manager.connect(user_id, websocket)
    await websocket.send_json({"type": "connected", "userId": user_id})

    heartbeat_task = asyncio.create_task(_send_heartbeats(websocket))
    try:
        while True:
            message = await websocket.receive_json()
            await _handle_client_message(websocket, message, subscriptions)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001 - a malformed frame or any
        # other per-connection failure must close only THIS connection,
        # never take down the whole realtime router for other clients.
        logger.warning("realtime.connection_error", user_id=user_id, error=str(exc))
    finally:
        heartbeat_task.cancel()
        await connection_manager.disconnect(user_id, websocket)


async def _send_heartbeats(websocket: WebSocket) -> None:
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            await websocket.send_json({"type": "heartbeat"})
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 - the connection is already going
        # away (send failed); the outer handler's finally block performs
        # the actual cleanup, this task just needs to stop quietly.
        pass


async def _handle_client_message(
    websocket: WebSocket, message: dict[str, object], subscriptions: SubscriptionRegistry
) -> None:
    action = message.get("action")
    if action == "ping":
        await websocket.send_json({"type": "pong"})
        return
    if action == "subscribe":
        topics = message.get("topics")
        if isinstance(topics, list):
            subscriptions.subscribe(str(topic) for topic in topics)
        return
    if action == "unsubscribe":
        topics = message.get("topics")
        if isinstance(topics, list):
            subscriptions.unsubscribe(str(topic) for topic in topics)
        return
    await websocket.send_json({"type": "error", "message": f"Unknown action: {action!r}"})
