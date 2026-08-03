"""Shared httpx.AsyncClient for the AI proxy — a single long-lived
connection pool reused across every request to ai-service, instead of a
fresh httpx.AsyncClient (and its own TCP/TLS handshake) being created and
torn down on every individual AI-proxy call.

Follows the same @lru_cache singleton pattern as
src.infrastructure.persistence.redis.clients.get_redis_clients — the
client is created once per process and reused; HttpAiServiceClient's own
constructor already supported accepting an injected client (its
`client` parameter), this module is what was missing to actually wire
one through get_ai_service_client() instead of always falling back to
per-request client creation.
"""

from __future__ import annotations

from functools import lru_cache

import httpx

from src.config import get_settings


@lru_cache
def get_ai_service_http_client() -> httpx.AsyncClient:
    settings = get_settings()
    return httpx.AsyncClient(timeout=settings.ai_service_request_timeout_seconds)
