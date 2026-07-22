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

from src.domain.auth.exceptions import InvalidTokenError, UserNotFoundError
from src.domain.auth.repositories import UserRepository
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.security.verification_token_store import VerificationTokenStore


@dataclass(frozen=True, slots=True)
class RequestEmailVerificationCommand:
    email: str


@dataclass(frozen=True, slots=True)
class RequestEmailVerificationResult:
    raw_token: str
    user_id: UserId


class RequestEmailVerificationUseCase:
    def __init__(
        self, user_repository: UserRepository, token_store: VerificationTokenStore
    ) -> None:
        self._user_repository = user_repository
        self._token_store = token_store

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
