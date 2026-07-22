"""Unit tests for LoginUseCase — covers success, invalid credentials
(existing user wrong password, nonexistent user), account lockout,
email-not-verified rejection, and login history/audit recording."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.auth.audit_logger import AuditLogger
from src.application.auth.login_use_case import LoginCommand, LoginUseCase
from src.domain.auth.entities import Role, User
from src.domain.auth.exceptions import (
    AccountLockedError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
)
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.rate_limiting.login_rate_limiter import LoginRateLimiter
from src.infrastructure.security.jwt_provider import JwtProvider
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from tests.unit.application.fakes import (
    FakeAuditLogRepository,
    FakeLoginHistoryRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)


class _FakeRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis — only the
    subset of the interface LoginRateLimiter actually calls."""

    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        value = self._store.get(key)
        return str(value) if value is not None else None

    async def incr(self, key: str) -> int:
        self._store[key] = self._store.get(key, 0) + 1
        return self._store[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass  # no-op — TTL simulation not needed for these tests

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def ttl(self, key: str) -> int:
        return 900 if key in self._store else -1


async def _make_verified_user(
    user_repo: FakeUserRepository,
    hasher: Argon2PasswordHasher,
    *,
    password: str = "correct-password-value",
) -> User:
    from src.domain.auth.value_objects import PlaintextPassword

    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email("verified@example.com"),
        hashed_password=hasher.hash(PlaintextPassword(password)),
        full_name="Verified User",
        role=Role.USER,
        token_version=0,
        email_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    await user_repo.save(user)
    return user


def _make_use_case() -> (
    tuple[LoginUseCase, FakeUserRepository, FakeLoginHistoryRepository, FakeAuditLogRepository]
):
    user_repo = FakeUserRepository()
    refresh_repo = FakeRefreshTokenRepository()
    history_repo = FakeLoginHistoryRepository()
    audit_repo = FakeAuditLogRepository()
    audit_logger = AuditLogger(audit_repo)
    rate_limiter = LoginRateLimiter(_FakeRedis())  # type: ignore[arg-type]
    hasher = Argon2PasswordHasher()
    jwt_provider = JwtProvider(
        current_kid="test-key",
        current_secret="test-secret-value-at-least-32-characters-long",
        access_token_ttl_minutes=15,
    )
    use_case = LoginUseCase(
        user_repo, refresh_repo, history_repo, audit_logger, rate_limiter, hasher, jwt_provider
    )
    return use_case, user_repo, history_repo, audit_repo


def _command(email: str, password: str) -> LoginCommand:
    return LoginCommand(
        email=email,
        password=password,
        ip_address="127.0.0.1",
        user_agent="pytest-agent",
        device_label="Test Runner",
    )


class TestLoginSuccess:
    async def test_successful_login_returns_tokens(self) -> None:
        use_case, user_repo, _, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        result = await use_case.execute(_command(str(user.email), "correct-password-value"))

        assert result.user_id == user.id
        assert result.access_token
        assert result.refresh_token

    async def test_successful_login_records_history_and_audit(self) -> None:
        use_case, user_repo, history_repo, audit_repo = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        await use_case.execute(_command(str(user.email), "correct-password-value"))

        history = await history_repo.list_for_user(user.id)
        assert len(history) == 1
        assert history[0].success is True

        assert any(e.action == "LOGIN_SUCCESS" for e in audit_repo.entries)

    async def test_successful_login_clears_rate_limit_counter(self) -> None:
        use_case, user_repo, _, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        # One failed attempt, then a successful one
        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(_command(str(user.email), "wrong-password-value"))

        await use_case.execute(_command(str(user.email), "correct-password-value"))

        status = await use_case._rate_limiter.get_status(str(user.email))
        assert status.failed_count == 0


class TestLoginInvalidCredentials:
    async def test_wrong_password_for_existing_user_raises(self) -> None:
        use_case, user_repo, _, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(_command(str(user.email), "wrong-password-value"))

    async def test_nonexistent_user_raises_the_same_error_type(self) -> None:
        use_case, _, _, _ = _make_use_case()
        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(_command("nobody@example.com", "some-password-value"))

    async def test_failed_login_does_not_record_history_for_unknown_user(self) -> None:
        # No user_id to attach the history entry to (ADR-0002 is user-scoped)
        use_case, _, history_repo, _ = _make_use_case()
        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(_command("nobody@example.com", "some-password-value"))
        assert len(history_repo.entries) == 0

    async def test_failed_login_for_existing_user_records_failure_history(self) -> None:
        use_case, user_repo, history_repo, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        with pytest.raises(InvalidCredentialsError):
            await use_case.execute(_command(str(user.email), "wrong-password-value"))

        history = await history_repo.list_for_user(user.id)
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].failure_reason == "invalid_credentials"


class TestLoginAccountLockout:
    async def test_account_locks_after_threshold_failed_attempts(self) -> None:
        use_case, user_repo, _, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)

        for _ in range(10):
            with pytest.raises((InvalidCredentialsError, AccountLockedError)):
                await use_case.execute(_command(str(user.email), "wrong-password-value"))

        with pytest.raises(AccountLockedError):
            await use_case.execute(_command(str(user.email), "correct-password-value"))


class TestLoginEmailVerification:
    async def test_unverified_email_cannot_login_even_with_correct_password(self) -> None:
        use_case, user_repo, _, _ = _make_use_case()
        hasher = Argon2PasswordHasher()
        user = await _make_verified_user(user_repo, hasher)
        user.email_verified_at = None  # simulate unverified
        await user_repo.save(user)

        with pytest.raises(EmailNotVerifiedError):
            await use_case.execute(_command(str(user.email), "correct-password-value"))
