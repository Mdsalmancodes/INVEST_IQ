"""DI factories for Phase 9's real-time infrastructure — matches the
existing presentation/dependencies/*.py convention (FastAPI Depends()
composition, no custom container).

ConnectionManager is process-wide singleton state (it IS the registry of
this process's live WebSocket connections) — @lru_cache here plays the
same role it does for get_redis_clients() (Phase 1) and get_settings()
(Phase 1): one instance per process, resolved lazily on first use.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.infrastructure.persistence.redis.clients import RedisClients, get_redis_clients
from src.infrastructure.realtime.connection_manager import ConnectionManager
from src.infrastructure.realtime.redis_broker import RedisBroker


@lru_cache
def get_connection_manager() -> ConnectionManager:
    return ConnectionManager()


def get_redis_broker(
    redis_clients: Annotated[RedisClients, Depends(get_redis_clients)],
) -> RedisBroker:
    return RedisBroker(redis_clients.broker)
