"""Domain exceptions for the notifications bounded context.

Per Document 5 §14.3: domain layer raises specific exceptions, never
generic Exception; the presentation layer's centralized exception handler
maps each of these to an HTTP status, matching alert_exception_handlers.py
and watchlist_exception_handlers.py's pattern.
"""

from __future__ import annotations


class NotificationDomainError(Exception):
    """Base class for all notification domain exceptions."""


class NotificationNotFoundError(NotificationDomainError):
    pass


class NotificationOwnershipError(NotificationDomainError):
    """Raised when an operation is attempted on a notification the current
    user does not own — Document 3 §7.5's resource-level ownership rule,
    applied to the notifications context (matches AlertOwnershipError)."""


class InvalidDigestFrequencyError(NotificationDomainError):
    """Raised for an unrecognized digest_frequency — the domain-level
    companion to the DB's ck_notification_prefs_digest CHECK constraint."""
