"""Domain exceptions for the alerts bounded context.

Per Document 5 §14.3: domain layer raises specific exceptions, never
generic Exception; the presentation layer's centralized exception handler
maps each of these to an HTTP status, matching the established
watchlist/portfolio/market_data exception-mapping pattern.
"""

from __future__ import annotations


class AlertDomainError(Exception):
    """Base class for all alert domain exceptions."""


class AlertNotFoundError(AlertDomainError):
    pass


class AlertOwnershipError(AlertDomainError):
    """Raised when an operation is attempted on an alert the current user
    does not own — Document 3 §7.5's resource-level ownership rule,
    applied to the alerts context (matches WatchlistOwnershipError)."""


class InvalidAlertConditionError(AlertDomainError):
    """Raised for an unrecognized condition_type — the domain-level
    companion to the DB's ck_alerts_condition_type CHECK constraint, so
    the rule is enforced before a repository round-trip."""


class InvalidCooldownError(AlertDomainError):
    """Raised for a negative cooldown_minutes — the domain-level companion
    to the DB's ck_alerts_cooldown_non_negative CHECK constraint."""


class DuplicateAlertError(AlertDomainError):
    """Raised when creating an alert whose (user_id, instrument_id,
    condition_type, threshold) tuple already exists — mirrors the DB's
    uq_alerts_duplicate UNIQUE constraint at the domain layer too, so the
    invariant is enforced before a repository round-trip."""
