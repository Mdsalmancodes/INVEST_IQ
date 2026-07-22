"""Celery application setup for the market-data ingestion pipeline.

Per Document 5 §11.3: "Enqueue a Celery backfill task (`market-data`
queue)." Uses the redis-broker instance (Document 3 §7.7's 3-way split) —
NOT redis-cache (which the market data quote cache uses) or redis-session,
keeping Celery's own broker traffic isolated from both, per the frozen
architecture's stated rationale for the 3-way split.
"""

from __future__ import annotations

from celery import Celery

from src.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "investiq_core_api",
        broker=str(settings.redis_broker_url),
        backend=str(settings.redis_broker_url),
    )
    app.conf.update(
        task_default_queue="market-data",
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = create_celery_app()
