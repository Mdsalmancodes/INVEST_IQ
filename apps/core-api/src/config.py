"""Centralized, validated configuration for core-api.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §17.2: all
configuration via environment variables, loaded through a single validated
config module — no scattered os.environ.get() calls throughout the codebase.
Uses pydantic-settings (not a custom parser) per the "prefer a mature
library" directive.

Fail-fast principle (same section): a missing/invalid required environment
variable crashes the service at startup, never at first-request-that-needs-it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    service_name: str = "core-api"

    # Database — Postgres is the source of truth for all financial data
    # (Document 3 §8.1). Required; no default, so a missing value fails fast.
    database_url: PostgresDsn

    # Redis — split into 3 instances by workload per Document 3 §7.7's
    # post-review revision (cache / broker+streams / session). Each has its
    # own URL so they can point at genuinely separate instances in staging/
    # production, while local dev docker-compose can point all three at
    # distinct containers on the same host (see infra/docker-compose.yml).
    redis_cache_url: RedisDsn
    redis_broker_url: RedisDsn
    redis_session_url: RedisDsn

    # Auth (Document 3 §7.4)
    jwt_secret: SecretStr
    jwt_kid: str = "default"
    jwt_previous_secret: SecretStr | None = None
    jwt_previous_kid: str | None = None
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    @field_validator("jwt_secret")
    @classmethod
    def _validate_jwt_secret_length(cls, value: SecretStr) -> SecretStr:
        # RFC 7518 §3.2 recommends HMAC keys be at least as long as the hash
        # output (32 bytes for HS256) — enforced here rather than left to be
        # silently accepted and only flagged as a runtime warning by PyJWT.
        if len(value.get_secret_value()) < 32:
            raise ValueError(
                "jwt_secret must be at least 32 characters (RFC 7518 §3.2 minimum for HS256)"
            )
        return value

    # AI service integration — Document 3 §7.1's MockAiServiceClient pattern:
    # local dev without the "ml" compose profile running talks to a mock
    # implementation of the same interface rather than a real ai-service call.
    ai_service_mode: Literal["mock", "live"] = "mock"
    ai_service_base_url: str = "http://ai-service:8000"

    # CORS — populated per-environment; empty by default so an unconfigured
    # deployment fails closed, not open.
    cors_allowed_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, resolved once per process.

    Exposed as a FastAPI dependency (see dependencies.py) rather than a bare
    module-level singleton, so tests can override it via FastAPI's
    `app.dependency_overrides` without monkeypatching module state.
    """
    return Settings()
