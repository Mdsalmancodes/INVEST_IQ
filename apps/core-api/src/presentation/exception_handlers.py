"""Centralized exception handling — Document 5 §14.3: domain exceptions are
mapped to HTTP status + the standard error envelope in ONE place. Adding a
new domain exception requires registering its mapping here.

Note: this module maps exceptions to (status_code, error_code, message)
tuples rather than registering FastAPI exception handlers directly, because
auth_router.py's endpoints catch domain exceptions explicitly and call
`raise_as_http()` — this keeps the mapping table centralized while still
letting each endpoint control precisely which exceptions it expects (a
route that can raise UserAlreadyExistsError but not TokenExpiredError
shouldn't silently swallow an unrelated exception type it never expected).
"""

from __future__ import annotations

from fastapi import HTTPException, status

from src.domain.auth.exceptions import (
    AccountLockedError,
    AuthDomainError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidEmailError,
    InvalidPasswordError,
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)

_EXCEPTION_STATUS_MAP: dict[type[AuthDomainError], int] = {
    InvalidEmailError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidPasswordError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    WeakPasswordError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    UserAlreadyExistsError: status.HTTP_409_CONFLICT,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    EmailNotVerifiedError: status.HTTP_403_FORBIDDEN,
    TokenExpiredError: status.HTTP_401_UNAUTHORIZED,
    TokenRevokedError: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenError: status.HTTP_400_BAD_REQUEST,
}


def raise_as_http(exc: AuthDomainError) -> None:
    """Translates a caught domain exception into the corresponding
    HTTPException and raises it. AccountLockedError is handled separately
    (below) since it carries extra data (retry_after_seconds) the generic
    map doesn't accommodate.
    """
    if isinstance(exc, AccountLockedError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), status.HTTP_400_BAD_REQUEST)
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc
