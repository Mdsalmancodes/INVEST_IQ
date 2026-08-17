"""
INVEST IQ observability utilities.

Responsibilities
----------------
- Configure application logging.
- Provide named loggers.
- Keep logging configuration centralized.
- Avoid external observability dependencies during local development.

This module intentionally contains infrastructure-level logging helpers
only. It does not contain business logic.
"""

from __future__ import annotations

import logging
import sys
from typing import Final


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_LOG_LEVEL: Final[str] = "INFO"

_LOG_FORMAT: Final[str] = (
    "%(asctime)s | "
    "%(levelname)s | "
    "%(name)s | "
    "%(message)s"
)

_configured: bool = False


# ============================================================================
# LOG LEVEL
# ============================================================================


def _resolve_log_level(
    level: str | int | None,
) -> int:
    """
    Convert a configured logging level into a logging module level.

    Supported string values include:

        DEBUG
        INFO
        WARNING
        ERROR
        CRITICAL
    """

    if level is None:
        return logging.INFO

    if isinstance(level, int):
        return level

    normalized = str(level).strip().upper()

    resolved = getattr(
        logging,
        normalized,
        None,
    )

    if isinstance(resolved, int):
        return resolved

    return logging.INFO


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================


def configure_logging(
    service_name: str = "invest-iq-ai-service",
    level: str | int | None = DEFAULT_LOG_LEVEL,
) -> None:
    """
    Configure application-wide logging.

    Calling this function multiple times is safe.

    Parameters
    ----------
    service_name:
        Logical service name used in the logger namespace.

    level:
        Logging level such as INFO, DEBUG, WARNING, ERROR, or CRITICAL.
    """

    global _configured

    resolved_level = _resolve_log_level(
        level
    )

    root_logger = logging.getLogger()

    # ------------------------------------------------------------------------
    # Configure the root logger only once.
    # ------------------------------------------------------------------------

    if not _configured:

        handler = logging.StreamHandler(
            sys.stdout
        )

        formatter = logging.Formatter(
            _LOG_FORMAT
        )

        handler.setFormatter(
            formatter
        )

        root_logger.handlers.clear()

        root_logger.addHandler(
            handler
        )

        _configured = True

    root_logger.setLevel(
        resolved_level
    )

    # ------------------------------------------------------------------------
    # Configure the INVEST IQ service logger.
    # ------------------------------------------------------------------------

    service_logger = logging.getLogger(
        service_name
    )

    service_logger.setLevel(
        resolved_level
    )

    service_logger.propagate = True


# ============================================================================
# LOGGER FACTORY
# ============================================================================


def get_logger(
    name: str | None = None,
) -> logging.Logger:
    """
    Return a logger for the requested module.

    Example
    -------

        logger = get_logger(__name__)

        logger.info(
            "service.startup"
        )
    """

    logger_name = (
        name
        if name
        else "invest-iq"
    )

    return logging.getLogger(
        logger_name
    )


# ============================================================================
# PUBLIC API
# ============================================================================


__all__ = [
    "configure_logging",
    "get_logger",
]