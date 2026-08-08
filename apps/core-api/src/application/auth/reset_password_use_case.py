"""RequestPasswordResetUseCase / ResetPasswordUseCase — Document 3 §7.4's
password reset flow, using the same opaque-token pattern as email
verification but a shorter TTL (1 hour, Document commentary in
verification_token_store.py) given the more sensitive capability it grants.

ResetPassword also invalidates all other sessions (Document 6 §15.6 lists
"password change" as a security-relevant event) — matching User.change_
password's own behavior, since a password reset is semantically a password
change triggered via a different entry point. Phase 8 additionally records
this event via AuditLogger — Document 6 §15.6 explicitly names "password
change" in its required audit-logged actions list, and login_use_case.py
already established the AuditLogger.record() call pattern this reuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from observability import get_logger

from src.application.auth.audit_logger import AuditLogger
from src.domain.auth.exceptions import InvalidTokenError, UserNotFoundError, WeakPasswordError
from src.domain.auth.repositories import RefreshTokenRepository, UserRepository
from src.domain.auth.value_objects import Email, PlaintextPassword, UserId
from src.infrastructure.security.common_password_blocklist import is_common_password
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from src.infrastructure.security.verification_token_store import VerificationTokenStore

if TYPE_CHECKING:
    from src.infrastructure.email.email_service import EmailService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RequestPasswordResetCommand:
    email: str


@dataclass(frozen=True, slots=True)
class RequestPasswordResetResult:
    raw_token: str
    user_id: UserId


class RequestPasswordResetUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        token_store: VerificationTokenStore,
        email_service: EmailService | None = None,
    ) -> None:
        self._user_repository = user_repository
        self._token_store = token_store
        self._email_service = email_service

    async def execute(
        self, command: RequestPasswordResetCommand
    ) -> RequestPasswordResetResult | None:
        """Returns None if no account exists — same enumeration-mitigation
        requirement as RequestEmailVerificationUseCase."""
        user = await self._user_repository.get_by_email(Email(command.email))
        if user is None or user.is_oauth_only:
            # OAuth-only accounts have no password to reset (Document 3 §8.1:
            # hashed_password is NULL for OAuth-only accounts) — silently
            # returning None here (rather than a distinct error) keeps this
            # endpoint's response shape identical to the "no such user" case,
            # for the same enumeration-mitigation reason.
            return None
        raw_token = await self._token_store.issue(str(user.id))

        # Send password reset email — failures are logged but never prevent
        # the token from being issued. The user can request another email.
        if self._email_service is not None:
            try:
                sent = await self._email_service.send_password_reset_email(
                    command.email, raw_token
                )
                if not sent:
                    logger.warning(
                        "email.password_reset.delivery_failed",
                        recipient=command.email,
                        user_id=str(user.id),
                    )
            except Exception:
                logger.error(
                    "email.password_reset.send_error",
                    recipient=command.email,
                    user_id=str(user.id),
                    exc_info=True,
                )

        return RequestPasswordResetResult(raw_token=raw_token, user_id=user.id)


@dataclass(frozen=True, slots=True)
class ResetPasswordCommand:
    raw_token: str
    new_password: str


class ResetPasswordUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        token_store: VerificationTokenStore,
        password_hasher: Argon2PasswordHasher,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._user_repository = user_repository
        self._refresh_token_repository = refresh_token_repository
        self._token_store = token_store
        self._password_hasher = password_hasher
        self._audit_logger = audit_logger

    async def execute(self, command: ResetPasswordCommand) -> UserId:
        new_password = PlaintextPassword(command.new_password)
        if is_common_password(new_password.value):
            raise WeakPasswordError(
                "This password is too common. Please choose a stronger password."
            )

        user_id_str = await self._token_store.consume(command.raw_token)
        if user_id_str is None:
            raise InvalidTokenError("Password reset link is invalid or has expired")

        user_id = UserId.from_string(user_id_str)
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User for this reset token no longer exists")

        user.change_password(self._password_hasher.hash(new_password))
        await self._user_repository.save(user)

        # change_password() already bumped token_version (invalidating
        # access tokens); explicitly revoke refresh tokens too so a stolen
        # refresh token also stops working immediately, not just on its
        # next (already-blocked-by-version-check) access token exchange.
        await self._refresh_token_repository.revoke_all_for_user(user.id, datetime.now(UTC))

        if self._audit_logger is not None:
            await self._audit_logger.record(
                action="auth.password_change",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
            )

        return user.id
