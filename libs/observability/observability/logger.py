"""Structured JSON logging, shared across all backend services — built on structlog.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md §14.1:
one JSON log line per event, with requestId propagation (§14.2) and automatic
redaction. Per the "prefer a mature library over reinventing infrastructure"
directive, this wraps structlog rather than a hand-rolled formatter — structlog
already solves stdlib-logging integration, JSON rendering, and context
propagation (contextvars) correctly; our job is only to configure its
processor chain with our domain-specific redaction policy and field names.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from observability.redaction import redaction_processor


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Configure structlog (+ stdlib logging) to emit structured JSON to stdout.

    Call once at service startup (e.g. in main.py's app factory). Idempotent —
    safe to call multiple times (e.g. in tests).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.stdlib.ExtraAdder(),
            _add_service_name(service_name),
            redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_service_name(
    service_name: str,
) -> Any:
    def processor(
        logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict["service"] = service_name
        return event_dict

    return processor


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given module name.

    Usage: ``logger = get_logger(__name__)`` then
    ``logger.info("portfolio.transaction.recorded", request_id=rid, portfolio_id=pid)``.
    Bind request-scoped context once per request (e.g. in BFF/middleware) via
    ``structlog.contextvars.bind_contextvars(request_id=rid)`` — it then
    propagates automatically to every log call within that request without
    threading it through every function signature.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
