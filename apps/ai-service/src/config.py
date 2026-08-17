"""Centralized, validated configuration for ai-service.

Per docs/architecture/07-devops-cicd-deployment-scalability.md §17.2,
this follows the same fail-fast configuration pattern as core-api.

Phase 7 adds the settings required by the Hybrid AI/ML Engine:

- core-api base URL for the HTTP-based MarketDataRepository
- trained ML model artifact storage
- model registry metadata storage
- prediction-run storage

The frozen architecture specifies S3-compatible object storage and MongoDB
for production. Neither is configured in this local environment, so the
repository abstractions currently persist to the local filesystem.

This keeps the application/domain layers independent from the storage
implementation and allows the infrastructure implementation to be replaced
later without changing the application logic.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized ai-service configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ======================================================================
    # SERVICE
    # ======================================================================

    environment: Literal[
        "local",
        "ci",
        "staging",
        "production",
    ] = "local"

    log_level: str = "INFO"

    service_name: str = "ai-service"

    # ======================================================================
    # REDIS
    # ======================================================================

    # ai-service uses Redis for:
    #
    # - prediction/result caching
    # - Celery broker
    # - Celery result backend
    #
    # Session management belongs to core-api and is not owned by ai-service.

    redis_cache_url: RedisDsn

    redis_broker_url: RedisDsn

    # ======================================================================
    # CORE API
    # ======================================================================

    core_api_base_url: str = "http://core-api:8000"

    """Base URL of the existing core-api.

    ai-service reuses core-api's Market Data module instead of maintaining
    a second direct connection to the market-data database.

    The MarketDataRepository therefore calls core-api over HTTP for
    historical OHLCV data.
    """

    # ======================================================================
    # ML ARTIFACT STORAGE
    # ======================================================================

    ml_artifact_storage_path: str = "./data/models"

    """Local filesystem root for trained ML model artifacts.

    Examples:

        ./data/models/
            lstm/
                AAPL/
                    <version>.pt

            arima/
                AAPL/
                    <version>.pkl

            prophet/
                AAPL/
                    <version>.pkl

            random_forest/
                AAPL/
                    <version>.pkl

            xgboost/
                AAPL/
                    <version>.pkl

    This path is used by:

        - ModelLoader
        - TrainModelUseCase
        - RetrainModelUseCase

    It stores the actual trained model files.
    """

    # ======================================================================
    # ML MODEL REGISTRY
    # ======================================================================

    ml_model_registry_storage_path: str = "./data/model_registry"

    """Local filesystem root for ModelVersion registry metadata.

    Examples:

        ./data/model_registry/
            lstm/
                <model-version-id>.json

            arima/
                <model-version-id>.json

            prophet/
                <model-version-id>.json

            random_forest/
                <model-version-id>.json

            xgboost/
                <model-version-id>.json

    These JSON files contain metadata such as:

        - model version ID
        - model family
        - stock symbol
        - artifact location
        - training timestamp
        - training data range
        - validation metrics
        - rollout percentage
        - status

    IMPORTANT:

        This is intentionally separate from
        ml_artifact_storage_path.

        ml_artifact_storage_path
            -> actual .pt / .pkl model files

        ml_model_registry_storage_path
            -> ModelVersion JSON metadata
    """

    # ======================================================================
    # PREDICTION RUN STORAGE
    # ======================================================================

    ml_prediction_run_storage_path: str = "./data/prediction_runs"

    """Local filesystem root for persisted PredictionRun records.

    This is the local-disk implementation used in the current environment
    as a substitute for the production MongoDB-backed repository.
    """

    # ======================================================================
    # INTERNAL SERVICE SECURITY
    # ======================================================================

    internal_service_token: str = (
        "change-me-in-every-real-environment"
    )

    """Internal authentication token shared with core-api.

    Every protected /api/v1/ml/* request must provide the matching
    X-Internal-Service-Token header.

    Only core-api's AiServiceClient should know and send this token.

    /health and /metrics remain publicly accessible inside the deployment
    environment so infrastructure health checks and monitoring systems can
    access them.

    IMPORTANT:

        The default value is intended only for local development.

        Production/staging deployments MUST override this value through
        the environment configuration.
    """


# ==========================================================================
# SETTINGS DEPENDENCY
# ==========================================================================


@lru_cache
def get_settings() -> Settings:
    """Return the cached ai-service Settings instance.

    FastAPI dependencies can override this function during tests using
    app.dependency_overrides.
    """

    return Settings()