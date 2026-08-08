"""RequestEmailVerificationUseCase / VerifyEmailUseCase — Document 3 §7.4's
email verification flow: `RegisterUseCase` creates a user with
`email_verified_at = None`; a verification link (containing an opaque token,
per src.infrastructure.security.verification_token_store) is issued
separately and consumed here to mark the email verified.

Split into two use cases (request + verify) rather than one, since
"request" can legitimately be called again (resend link) independent of
"verify" — collapsing them would make resend impossible to express cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from observability import get_logger

from src.domain.auth.exceptions import InvalidTokenError, UserNotFoundError
from src.domain.auth.repositories import UserRepository
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.security.verification_token_store import VerificationTokenStore

if TYPE_CHECKING:
    from src.infrastructure.email.email_service import EmailService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RequestEmailVerificationCommand:
    email: str


@dataclass(frozen=True, slots=True)
class RequestEmailVerificationResult:
    raw_token: str
    user_id: UserId


class RequestEmailVerificationUseCase:
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
        self, command: RequestEmailVerificationCommand
    ) -> RequestEmailVerificationResult | None:
        """Returns None if no account exists for the email — the presentation
        layer must respond identically either way (Document 6 §15.1
        enumeration mitigation: "does this email exist" must never be
        observable from this endpoint's response)."""
        user = await self._user_repository.get_by_email(Email(command.email))
        if user is None or user.is_email_verified:
            return None
        raw_token = await self._token_store.issue(str(user.id))

        # Send verification email — failures are logged but never prevent
        # the token from being issued. The user can request another email.
        if self._email_service is not None:
            try:
                sent = await self._email_service.send_verification_email(
                    command.email, raw_token
                )
                if not sent:
                    logger.warning(
                        "email.verification.delivery_failed",
                        recipient=command.email,
                        user_id=str(user.id),
                    )
            except Exception:
                logger.error(
                    "email.verification.send_error",
                    recipient=command.email,
                    user_id=str(user.id),
                    exc_info=True,
                )

        return RequestEmailVerificationResult(raw_token=raw_token, user_id=user.id)


@dataclass(frozen=True, slots=True)
class VerifyEmailCommand:
    raw_token: str


class VerifyEmailUseCase:
    def __init__(
        self, user_repository: UserRepository, token_store: VerificationTokenStore
    ) -> None:
        self._user_repository = user_repository
        self._token_store = token_store

    async def execute(self, command: VerifyEmailCommand) -> UserId:
        user_id_str = await self._token_store.consume(command.raw_token)
        if user_id_str is None:
            raise InvalidTokenError("Verification link is invalid or has expired")

        user_id = UserId.from_string(user_id_str)
        user = await self._user_repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User for this verification token no longer exists")

        user.mark_email_verified(datetime.now(UTC))
        await self._user_repository.save(user)
        return user.id
