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

    # Phase 8 — Enterprise Security. "AI Service must never be directly
    # exposed" is enforced by ai-service's own InternalServiceAuthMiddleware
    # rejecting any /api/v1/ml/* request without this exact header value —
    # this setting MUST be identical to ai-service's own
    # INTERNAL_SERVICE_TOKEN. Only AiServiceClient (the sole caller of
    # ai-service from this codebase) ever reads or sends it.
    #
    # Required with no default (matching jwt_secret's fail-fast pattern
    # above) — this used to default to the placeholder string
    # "change-me-in-every-real-environment", which would have silently
    # worked (both core-api and ai-service would agree on the same
    # placeholder value) while providing zero actual security: anyone who
    # read this file's source would know the token for any misconfigured
    # deployment. Failing fast on a missing value forces every real
    # environment to set an actual secret.
    internal_service_token: SecretStr
    ai_service_request_timeout_seconds: float = 30.0
    """AI training endpoints can genuinely take longer than a typical API
    call (real model fitting, not a DB round-trip) — a longer default
    timeout than a bare httpx default avoids spurious timeouts on
    /train and /retrain specifically, while still bounding worst-case
    proxy latency for every other endpoint."""

    # General-purpose rate limiting (distinct from LoginRateLimiter, which
    # is login-attempt-specific per Document 6 §15.2). Applied by
    # RateLimitMiddleware to every request, keyed by authenticated user id
    # when available, else client IP. A stricter override applies
    # specifically to the AI proxy's expensive model train/retrain
    # endpoints (real model fitting, not a cheap DB read).
    rate_limit_requests_per_window: int = 100
    rate_limit_window_seconds: int = 60
    rate_limit_ai_training_requests_per_window: int = 5
    rate_limit_ai_training_window_seconds: int = 300

    # Phase 8 — Enterprise Security. Document 6 §15.6 names "large
    # transaction (> configurable threshold)" in its required audit-
    # logged actions list — AddTransactionUseCase (Phase 3, unmodified
    # otherwise) additionally records an audit entry when a transaction's
    # total value (price * quantity, or cash_amount for cash-only types)
    # meets or exceeds this threshold.
    large_transaction_audit_threshold_usd: float = 10_000.0

    # CORS — populated per-environment; empty by default so an unconfigured
    # deployment fails closed, not open.
    cors_allowed_origins: list[str] = Field(default_factory=list)

    # Phase 9 — Real-Time Market Intelligence. No genuinely continuous/
    # streaming market data provider exists in this dev environment
    # (yfinance, Document 5 §11.1, is a polling API, not a push/streaming
    # one — the same disclosed limitation Phase 4's background sync task
    # already carries). MarketDataStreamingService therefore polls on a
    # fixed interval and publishes each tick's result to Redis Pub/Sub;
    # this setting controls that interval. 5s is short enough to feel
    # "live" for a dashboard without hammering the underlying provider
    # far beyond what a free-tier/dev API can sustain across many symbols.
    realtime_market_data_poll_interval_seconds: float = 5.0

    # Phase 9 — "Live Watchlist." A separate, longer interval than raw
    # quote streaming — watchlist enrichment re-runs WatchlistEnrichmentService
    # (Phase 5) for every item in a user's watchlist(s), which is more
    # expensive per tick than a single symbol's quote lookup and doesn't
    # need to feel as instantaneous as the raw ticker; a longer interval
    # reduces redundant enrichment-service calls that mostly re-fetch the
    # same underlying quotes the market-data streaming loop already polls
    # more frequently.
    realtime_watchlist_poll_interval_seconds: float = 10.0

    # Phase 9 — "Live Portfolio." Comparable cost profile to watchlist
    # streaming (a full PortfolioCalculationService.compute_summary() call
    # across all holdings, plus a price lookup per holding, per tick) —
    # defaults to the same 10s interval for the same reason.
    realtime_portfolio_poll_interval_seconds: float = 10.0

    # Phase 9 — "Live AI." A full Decision Engine ensemble prediction
    # (LSTM/ARIMA/Prophet/RandomForest/XGBoost, ai-service's Phase 7
    # Decision Engine, proxied via the EXISTING Phase 8 AiServiceClient)
    # is far more expensive than a quote lookup or even a portfolio
    # recalculation — a materially longer default interval than every
    # other Phase 9 streaming loop reflects that real cost, not an
    # oversight. The founder's "whenever market data changes" trigger
    # condition is interpreted as "re-run on this service's own
    # independent interval" rather than literally diffing every price
    # tick server-side to detect "change," which the polling loop already
    # achieves the same practical effect as, without the added complexity.
    realtime_ai_poll_interval_seconds: float = 30.0

    # Phase 9 — "Live Sentiment." Shares the same underlying
    # get_recommendation() HTTP call AiPredictionStreamingService already
    # makes (see sentiment_streaming_service.py's module docstring for
    # the full disclosed design rationale — no live news/Reddit ingestion
    # pipeline exists, so this reuses the sentiment_score already
    # embedded in the Decision Engine's prediction output rather than
    # calling ai-service's dedicated /sentiment endpoint with fabricated
    # text). Same interval as the AI prediction loop since it is,
    # functionally, the same underlying computation.
    realtime_sentiment_poll_interval_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance, resolved once per process.

    Exposed as a FastAPI dependency (see dependencies.py) rather than a bare
    module-level singleton, so tests can override it via FastAPI's
    `app.dependency_overrides` without monkeypatching module state.
    """
    return Settings()
