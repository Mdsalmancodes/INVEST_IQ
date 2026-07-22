"""Centralized, validated configuration for ai-service — infrastructure skeleton only.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §17.2, same
fail-fast pattern as core-api (src/config.py there). Phase 1 scope only:
enough settings to run /health and /ready. Mongo connection settings,
model-serving config, Celery broker config, etc. (Document 4 §10) are added
when the corresponding business logic is built in Phase 7+ — not stubbed in
now with no consumer, per the "no business logic in Phase 1" instruction.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    service_name: str = "ai-service"

    # Redis — same 3-instance split as core-api (Document 3 §7.7). ai-service
    # only needs redis-cache and redis-broker in the frozen architecture
    # (prediction/screener result caching; Celery broker+result backend for
    # ml-inference/ml-training queues) — it has no session concept of its own.
    redis_cache_url: RedisDsn
    redis_broker_url: RedisDsn


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — exposed as a FastAPI dependency (see
    dependencies.py) so tests can override it via app.dependency_overrides.
    """
    return Settings()
