"""Redis client setup — 3 logically separate instances by workload.

Per docs/architecture/03-backend-architecture-database-design.md §7.7
(post-review revision): redis-cache (quotes/screener/prediction cache, no
persistence), redis-broker (Celery + Alert Streams, AOF-persisted),
redis-session (sessions/rate-limit counters, RDB snapshotting). Using
redis.asyncio's client directly (connection pooling included) rather than a
custom wrapper, per the "use the library" directive — application code only
adds behavior on top where the architecture genuinely requires it (e.g. the
SETNX-based stampede lock in a later phase), never for basic connectivity.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from redis.asyncio import Redis

from src.config import get_settings


@dataclass(frozen=True)
class RedisClients:
    cache: Redis
    broker: Redis
    session: Redis


@lru_cache
def get_redis_clients() -> RedisClients:
    settings = get_settings()
    return RedisClients(
        cache=Redis.from_url(str(settings.redis_cache_url), decode_responses=True),
        broker=Redis.from_url(str(settings.redis_broker_url), decode_responses=True),
        session=Redis.from_url(str(settings.redis_session_url), decode_responses=True),
    )
