"""Centralized, validated configuration for ai-service.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §17.2, same
fail-fast pattern as core-api (src/config.py there). Phase 7 (Document 4
§10) adds the settings the Hybrid AI/ML Engine actually needs: core-api's
base URL (for the HTTP-based MarketDataRepository — per the founder's
"reuse the existing Market Data module, never duplicate data" instruction,
ai-service never opens its own Postgres connection) and a local filesystem
path for model artifacts + prediction run records (disclosed in
docs/phase-7/known-issues.md — the frozen architecture specifies
S3-compatible object storage and MongoDB respectively; neither is
configured in this environment, so both persist to local disk behind the
same repository-Protocol abstractions, making a later swap to real object
storage/Mongo an infrastructure-only change).
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

    # Phase 7 — Hybrid AI/ML Engine settings.
    core_api_base_url: str = "http://127.0.0.1:8000"
    """Per the founder's instruction to reuse core-api's existing Market
    Data module rather than duplicate the ohlcv_bars table — ai-service
    calls core-api's already-public GET /api/v1/instruments/{symbol}/bars
    endpoint over HTTP for OHLCV history."""

    ml_artifact_storage_path: str = "./data/models"
    """Local filesystem root for trained model artifacts (ModelRegistryRepository)
    — disclosed local-disk substitute for the frozen architecture's
    S3-compatible object storage (see known-issues.md)."""

    ml_prediction_run_storage_path: str = "./data/prediction_runs"
    """Local filesystem root for persisted PredictionRun records
    (PredictionRunRepository) — disclosed local-disk substitute for the
    frozen architecture's MongoDB collection (see known-issues.md)."""

    # Phase 8 — Enterprise Security: "AI Service must never be directly
    # exposed" is enforced here, not just by docker-compose network
    # topology (which is a deployment convention, not a code-level
    # guarantee an auditor or test suite can verify). Every request to
    # /api/v1/ml/* must carry a matching X-Internal-Service-Token header,
    # which only core-api's AiServiceClient is configured to know and send
    # (see apps/core-api/src/infrastructure/http/ai_service_client.py).
    # /health and /metrics remain open (infra liveness/readiness probes and
    # monitoring scrapers are not core-api, and carry no user-identifying
    # data worth protecting behind the secret).
    internal_service_token: str = "change-me-in-every-real-environment"
    """Required, must be identical to core-api's own
    INTERNAL_SERVICE_TOKEN setting — validated by
    src/presentation/internal_auth_middleware.py on every /api/v1/ml/*
    request. The insecure literal default is intentional and matches this
    codebase's existing convention for local-dev-only secrets (e.g.
    apps/web/.env.example's NEXTAUTH_SECRET) — every real deployment
    environment MUST override it via the actual environment variable;
    docs/phase-8/known-issues.md discloses this explicitly rather than
    silently relying on the default being changed."""


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — exposed as a FastAPI dependency (see
    dependencies.py) so tests can override it via app.dependency_overrides.
    """
    return Settings()
