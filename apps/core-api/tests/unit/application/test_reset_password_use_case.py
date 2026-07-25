"""Unit tests for RequestPasswordResetUseCase and ResetPasswordUseCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.application.auth.reset_password_use_case import (
    RequestPasswordResetCommand,
    RequestPasswordResetUseCase,
    ResetPasswordCommand,
    ResetPasswordUseCase,
)
from src.domain.auth.entities import RefreshToken, Role, User
from src.domain.auth.exceptions import InvalidTokenError, WeakPasswordError
from src.domain.auth.value_objects import Email, PlaintextPassword, UserId
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)
from tests.unit.application.fake_token_store import FakeVerificationTokenStore
from tests.unit.application.fakes import FakeRefreshTokenRepository, FakeUserRepository


async def _make_password_user(
    user_repo: FakeUserRepository, hasher: Argon2PasswordHasher, *, oauth_only: bool = False
) -> User:
    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email("reset-test@example.com"),
        hashed_password=None
        if oauth_only
        else hasher.hash(PlaintextPassword("original-password-value")),
        full_name="Reset Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    await user_repo.save(user)
    return user


class TestRequestPasswordReset:
    async def test_issues_a_token_for_a_password_based_account(self) -> None:
        user_repo = FakeUserRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        use_case = RequestPasswordResetUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(RequestPasswordResetCommand(str(user.email)))

        assert result is not None
        assert result.user_id == user.id

    async def test_returns_none_for_unknown_email(self) -> None:
        user_repo = FakeUserRepository()
        use_case = RequestPasswordResetUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(RequestPasswordResetCommand("nobody@example.com"))

        assert result is None

    async def test_returns_none_for_oauth_only_account(self) -> None:
        user_repo = FakeUserRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher, oauth_only=True)
        use_case = RequestPasswordResetUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(RequestPasswordResetCommand(str(user.email)))

        assert result is None


class TestResetPassword:
    async def test_resets_password_with_a_valid_token(self) -> None:
        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        token_store = FakeVerificationTokenStore()

        request_use_case = RequestPasswordResetUseCase(user_repo, token_store)
        reset_use_case = ResetPasswordUseCase(user_repo, refresh_repo, token_store, hasher)

        issued = await request_use_case.execute(RequestPasswordResetCommand(str(user.email)))
        assert issued is not None

        await reset_use_case.execute(
            ResetPasswordCommand(issued.raw_token, "a-brand-new-strong-password")
        )

        stored = await user_repo.get_by_id(user.id)
        assert stored is not None
        assert stored.hashed_password is not None
        assert hasher.verify(
            PlaintextPassword("a-brand-new-strong-password"), stored.hashed_password
        )
        assert hasher.verify(
            PlaintextPassword("original-password-value"), stored.hashed_password
        ) is False

    async def test_reset_bumps_token_version_and_revokes_refresh_tokens(self) -> None:
        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        token_store = FakeVerificationTokenStore()

        raw_refresh = generate_refresh_token()
        now = datetime.now(UTC)
        await refresh_repo.save(
            RefreshToken(
                id=UserId.new(),
                user_id=user.id,
                token_hash=hash_refresh_token(raw_refresh),
                expires_at=now + timedelta(days=30),
                created_at=now,
            )
        )

        request_use_case = RequestPasswordResetUseCase(user_repo, token_store)
        reset_use_case = ResetPasswordUseCase(user_repo, refresh_repo, token_store, hasher)
        issued = await request_use_case.execute(RequestPasswordResetCommand(str(user.email)))
        assert issued is not None

        await reset_use_case.execute(
            ResetPasswordCommand(issued.raw_token, "a-brand-new-strong-password")
        )

        stored_user = await user_repo.get_by_id(user.id)
        assert stored_user is not None
        assert stored_user.token_version == 1

        stored_token = await refresh_repo.get_by_token_hash(hash_refresh_token(raw_refresh))
        assert stored_token is not None
        assert stored_token.is_revoked is True

    async def test_rejects_invalid_token(self) -> None:
        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        use_case = ResetPasswordUseCase(
            user_repo, refresh_repo, FakeVerificationTokenStore(), hasher
        )

        with pytest.raises(InvalidTokenError):
            await use_case.execute(
                ResetPasswordCommand("never-issued-token", "a-brand-new-strong-password")
            )

    async def test_rejects_weak_new_password(self) -> None:
        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        token_store = FakeVerificationTokenStore()

        request_use_case = RequestPasswordResetUseCase(user_repo, token_store)
        reset_use_case = ResetPasswordUseCase(user_repo, refresh_repo, token_store, hasher)
        issued = await request_use_case.execute(RequestPasswordResetCommand(str(user.email)))
        assert issued is not None

        with pytest.raises(WeakPasswordError):
            await reset_use_case.execute(ResetPasswordCommand(issued.raw_token, "1234567890"))

    async def test_records_a_password_change_audit_entry_when_a_logger_is_injected(
        self,
    ) -> None:
        from src.application.auth.audit_logger import AuditLogger
        from tests.unit.application.fakes import FakeAuditLogRepository

        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        token_store = FakeVerificationTokenStore()
        audit_repo = FakeAuditLogRepository()
        audit_logger = AuditLogger(audit_repo)

        request_use_case = RequestPasswordResetUseCase(user_repo, token_store)
        reset_use_case = ResetPasswordUseCase(
            user_repo, refresh_repo, token_store, hasher, audit_logger=audit_logger
        )
        issued = await request_use_case.execute(RequestPasswordResetCommand(str(user.email)))
        assert issued is not None

        await reset_use_case.execute(
            ResetPasswordCommand(issued.raw_token, "a-brand-new-strong-password")
        )

        assert len(audit_repo.entries) == 1
        assert audit_repo.entries[0].action == "auth.password_change"
        assert audit_repo.entries[0].user_id == user.id

    async def test_works_without_an_audit_logger_injected_at_all(self) -> None:
        # Backward-compatible constructor default (audit_logger=None) —
        # every pre-Phase-8 call site/test continues to work unchanged.
        user_repo = FakeUserRepository()
        refresh_repo = FakeRefreshTokenRepository()
        hasher = Argon2PasswordHasher()
        user = await _make_password_user(user_repo, hasher)
        token_store = FakeVerificationTokenStore()

        request_use_case = RequestPasswordResetUseCase(user_repo, token_store)
        reset_use_case = ResetPasswordUseCase(user_repo, refresh_repo, token_store, hasher)
        issued = await request_use_case.execute(RequestPasswordResetCommand(str(user.email)))
        assert issued is not None

        await reset_use_case.execute(
            ResetPasswordCommand(issued.raw_token, "a-brand-new-strong-password")
        )  # should not raise
