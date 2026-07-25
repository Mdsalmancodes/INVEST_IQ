"""Domain exceptions for the AI/ML bounded context.

Per Document 5 §14.3's pattern (mirrored from core-api): domain layer
raises specific exceptions, never generic Exception; the presentation
layer's centralized exception handler maps each to an HTTP status.
"""

from __future__ import annotations


class MlDomainError(Exception):
    """Base class for all AI/ML domain exceptions."""


class InsufficientDataError(MlDomainError):
    """Raised when an instrument has less history than a model family's
    documented minimum (Document 4 §10.1a's per-model threshold table) —
    the domain-level signal that triggers ensemble exclusion, not a
    generic failure."""


class ModelUnavailableError(MlDomainError):
    """Raised when a model family cannot run in the current runtime
    environment (e.g. Prophet without a CmdStan backend — see
    known-issues.md) — distinct from InsufficientDataError, since this is
    an environment/infrastructure gap, not a data gap. Also triggers
    ensemble exclusion per Document 4 §10.1a's 'partialEnsemble' state."""


class PredictionRunNotFoundError(MlDomainError):
    pass


class ModelVersionNotFoundError(MlDomainError):
    pass


class InvalidForecastHorizonError(MlDomainError):
    pass
