"""Redis client setup for ai-service — cache + broker instances only.

Mirrors core-api's infrastructure/persistence/redis/clients.py (Document 3
§7.7). ai-service has no redis-session dependency of its own in the frozen
architecture (session state belongs to core-api).
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


@lru_cache
def get_redis_clients() -> RedisClients:
    settings = get_settings()
    return RedisClients(
        cache=Redis.from_url(str(settings.redis_cache_url), decode_responses=True),
        broker=Redis.from_url(str(settings.redis_broker_url), decode_responses=True),
    )
