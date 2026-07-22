"""Shared observability primitives for INVEST IQ backend services.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md §14.1:
every service logs structured JSON (never plain strings) through this shared
logger, with automatic secret redaction applied recursively before any log
line is emitted. Built on structlog (see logger.py) rather than a hand-rolled
formatter, per the "prefer a mature library" implementation directive.
"""

from observability.logger import configure_logging, get_logger
from observability.redaction import redact

__all__ = ["configure_logging", "get_logger", "redact"]
