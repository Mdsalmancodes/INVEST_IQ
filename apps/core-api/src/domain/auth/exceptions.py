"""Domain exceptions for the auth bounded context.

Per docs/architecture/05-data-pipeline-notifications-caching-monitoring.md §14.3:
domain layer raises specific domain exceptions, never generic Exception,
never HTTP-aware — the presentation layer's centralized exception handler
(src.presentation.exception_handlers) maps each of these to an HTTP status.
"""

from __future__ import annotations


class AuthDomainError(Exception):
    """Base class for all auth domain exceptions."""


class InvalidEmailError(AuthDomainError):
    pass


class InvalidPasswordError(AuthDomainError):
    pass


class UserAlreadyExistsError(AuthDomainError):
    """Raised when registering an email that already has an account."""


class UserNotFoundError(AuthDomainError):
    pass


class InvalidCredentialsError(AuthDomainError):
    """Raised on login failure. Deliberately does not distinguish
    'wrong password' from 'no such user' in its message — that distinction
    must never be observable to a client (Document 6 §15.1 credential
    stuffing / enumeration mitigation)."""


class AccountLockedError(AuthDomainError):
    """Raised when login rate limiting (Document 6 §15.2) has locked the
    account after repeated failed attempts."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Account locked. Retry after {retry_after_seconds}s")


class EmailNotVerifiedError(AuthDomainError):
    pass


class TokenExpiredError(AuthDomainError):
    pass


class TokenRevokedError(AuthDomainError):
    """Raised when a refresh token has been explicitly revoked, or when
    reuse of an already-rotated token is detected (Document 3 §7.4's
    refresh-token-rotation reuse-detection requirement)."""


class InvalidTokenError(AuthDomainError):
    pass


class WeakPasswordError(AuthDomainError):
    """Raised when a password fails the common-password blocklist check
    (Document 6 §15.2) — distinct from InvalidPasswordError (length), which
    the value object itself enforces; this is an application-layer check
    against an external wordlist resource."""
