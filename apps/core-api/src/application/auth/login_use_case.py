"""LoginUseCase — Document 3 §7.4 login flow: credential validation,
rate limiting (Document 6 §15.2), login history (ADR-0002), audit logging
(Document 6 §15.6), and access+refresh token issuance.

Deliberately does not distinguish "wrong password" from "no such user" in
any externally-visible way (Document 6 §15.1 enumeration mitigation,
InvalidCredentialsError's own docstring) — this use case always runs the
password verification step even when the user doesn't exist, against a
dummy hash, to keep response timing consistent (a basic defense against
timing-based user enumeration).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.application.auth.audit_logger import AuditLogger
from src.domain.auth.entities import LoginHistoryEntry, RefreshToken, Role
from src.domain.auth.exceptions import AccountLockedError, InvalidCredentialsError
from src.domain.auth.repositories import (
    LoginHistoryRepository,
    RefreshTokenRepository,
    UserRepository,
)
from src.domain.auth.value_objects import Email, PlaintextPassword, UserId
from src.infrastructure.rate_limiting.login_rate_limiter import LoginRateLimiter
from src.infrastructure.security.jwt_provider import JwtProvider
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)

# A real Argon2 hash (computed once at import time via the actual hasher, not
# hand-crafted) of an arbitrary fixed value, used only as a dummy comparison
# target when no user exists — keeps verification cost/behavior consistent
# regardless of whether the account exists, without ever persisting or
# exposing this value.
#
# BUG CAUGHT BY TESTS (documented for traceability): an earlier version of
# this constant was a hand-fabricated string that was NOT a valid Argon2
# hash. argon2-cffi's `verify()` raised `VerificationError` ("Decoding
# failed") for that malformed hash instead of returning False, which would
# have propagated as an unhandled 500 on every login attempt against a
# nonexistent email — defeating the entire purpose of this constant (timing-
# consistent rejection) and breaking the enumeration mitigation it exists
# for. Fixed by computing a genuinely valid hash via the real hasher.
_DUMMY_HASH = Argon2PasswordHasher().hash(
    PlaintextPassword("dummy-value-never-used-as-a-real-password")
)

_REFRESH_TOKEN_TTL_DAYS = 30


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str
    ip_address: str | None
    user_agent: str | None
    device_label: str | None


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    refresh_token: str
    user_id: UserId
    role: Role


class LoginUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        login_history_repository: LoginHistoryRepository,
        audit_logger: AuditLogger,
        rate_limiter: LoginRateLimiter,
        password_hasher: Argon2PasswordHasher,
        jwt_provider: JwtProvider,
    ) -> None:
        self._user_repository = user_repository
        self._refresh_token_repository = refresh_token_repository
        self._login_history_repository = login_history_repository
        self._audit_logger = audit_logger
        self._rate_limiter = rate_limiter
        self._password_hasher = password_hasher
        self._jwt_provider = jwt_provider

    async def execute(self, command: LoginCommand) -> LoginResult:
        email = Email(command.email)

        status = await self._rate_limiter.get_status(str(email))
        if status.is_locked:
            retry_after = await self._rate_limiter.get_retry_after_seconds(str(email))
            raise AccountLockedError(retry_after)

        user = await self._user_repository.get_by_email(email)
        password = PlaintextPassword(command.password)

        hash_to_check = (
            user.hashed_password
            if user is not None and user.hashed_password is not None
            else _DUMMY_HASH
        )
        password_ok = self._password_hasher.verify(password, hash_to_check)

        if user is None or user.is_oauth_only or not password_ok:
            await self._rate_limiter.record_failed_attempt(str(email))
            await self._record_login_history(
                user_id=user.id if user is not None else None,
                command=command,
                success=False,
                failure_reason="invalid_credentials",
            )
            await self._audit_logger.record(
                action="LOGIN_FAILED",
                user_id=user.id if user is not None else None,
                ip_address=command.ip_address,
            )
            raise InvalidCredentialsError("Invalid email or password")

        user.ensure_can_login_with_password()
        assert user.hashed_password is not None  # guaranteed by is_oauth_only check above

        if self._password_hasher.needs_rehash(user.hashed_password):
            user.hashed_password = self._password_hasher.hash(password)
            await self._user_repository.save(user)

        await self._rate_limiter.clear(str(email))
        await self._record_login_history(
            user_id=user.id, command=command, success=True, failure_reason=None
        )
        await self._audit_logger.record(
            action="LOGIN_SUCCESS", user_id=user.id, ip_address=command.ip_address
        )

        access_token = self._jwt_provider.issue_access_token(user.id, user.role, user.token_version)
        raw_refresh_token = generate_refresh_token()
        now = datetime.now(UTC)
        refresh_token_entity = RefreshToken(
            id=UserId.new(),
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh_token),
            expires_at=now + timedelta(days=_REFRESH_TOKEN_TTL_DAYS),
            created_at=now,
        )
        await self._refresh_token_repository.save(refresh_token_entity)

        return LoginResult(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            user_id=user.id,
            role=user.role,
        )

    async def _record_login_history(
        self,
        *,
        user_id: UserId | None,
        command: LoginCommand,
        success: bool,
        failure_reason: str | None,
    ) -> None:
        if user_id is None:
            return  # ADR-0002's login_history is user-scoped; no user to attach it to
        entry = LoginHistoryEntry(
            id=UserId.new(),
            user_id=user_id,
            ip_address=command.ip_address,
            user_agent=command.user_agent,
            device_label=command.device_label,
            success=success,
            failure_reason=failure_reason,
            created_at=datetime.now(UTC),
        )
        await self._login_history_repository.save(entry)
