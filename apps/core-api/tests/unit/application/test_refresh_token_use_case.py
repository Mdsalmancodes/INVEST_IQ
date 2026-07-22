"""Unit tests for RefreshTokenUseCase — rotation, expiry, and the
security-critical reuse-detection path (Document 3 §7.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.application.auth.refresh_token_use_case import (
    RefreshTokenCommand,
    RefreshTokenUseCase,
)
from src.domain.auth.entities import RefreshToken, Role, User
from src.domain.auth.exceptions import TokenExpiredError, TokenRevokedError
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.security.jwt_provider import JwtProvider
from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)
from tests.unit.application.fakes import FakeRefreshTokenRepository, FakeUserRepository


def _make_jwt_provider() -> JwtProvider:
    return JwtProvider(
        current_kid="test-key",
        current_secret="test-secret-value-at-least-32-characters-long",
        access_token_ttl_minutes=15,
    )


async def _make_user_with_token(
    user_repo: FakeUserRepository, token_repo: FakeRefreshTokenRepository, *, revoked: bool = False
) -> tuple[User, str]:
    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email("refresh-test@example.com"),
        hashed_password=None,
        full_name="Refresh Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    await user_repo.save(user)

    raw_token = generate_refresh_token()
    token = RefreshToken(
        id=UserId.new(),
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=now + timedelta(days=30),
        created_at=now,
        revoked_at=now if revoked else None,
    )
    await token_repo.save(token)
    return user, raw_token


class TestRefreshTokenRotation:
    async def test_successful_refresh_returns_new_tokens(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        user, raw_token = await _make_user_with_token(user_repo, token_repo)
        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())

        result = await use_case.execute(RefreshTokenCommand(raw_token))

        assert result.access_token
        assert result.refresh_token
        assert result.refresh_token != raw_token  # rotation issued a NEW token

    async def test_old_token_is_revoked_after_rotation(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        user, raw_token = await _make_user_with_token(user_repo, token_repo)
        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())

        await use_case.execute(RefreshTokenCommand(raw_token))

        old_token = await token_repo.get_by_token_hash(hash_refresh_token(raw_token))
        assert old_token is not None
        assert old_token.is_revoked is True

    async def test_new_token_can_be_used_for_a_further_refresh(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        _, raw_token = await _make_user_with_token(user_repo, token_repo)
        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())

        first_result = await use_case.execute(RefreshTokenCommand(raw_token))
        second_result = await use_case.execute(
            RefreshTokenCommand(first_result.refresh_token)
        )

        assert second_result.refresh_token != first_result.refresh_token


class TestRefreshTokenExpiry:
    async def test_expired_token_raises(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        now = datetime.now(UTC)
        user = User(
            id=UserId.new(),
            email=Email("expired@example.com"),
            hashed_password=None,
            full_name="Expired Token User",
            role=Role.USER,
            token_version=0,
            email_verified_at=now,
            created_at=now,
            updated_at=now,
        )
        await user_repo.save(user)
        raw_token = generate_refresh_token()
        expired_token = RefreshToken(
            id=UserId.new(),
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=now - timedelta(days=1),
            created_at=now - timedelta(days=31),
        )
        await token_repo.save(expired_token)

        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())
        with pytest.raises(TokenExpiredError):
            await use_case.execute(RefreshTokenCommand(raw_token))


class TestRefreshTokenReuseDetection:
    async def test_reusing_a_revoked_token_raises_and_revokes_all_sessions(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        user, raw_token = await _make_user_with_token(user_repo, token_repo)
        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())

        # First use: legitimate rotation.
        first_result = await use_case.execute(RefreshTokenCommand(raw_token))

        # Second use of the SAME (now-revoked) original token: this is the
        # replay/theft scenario Document 3 §7.4 requires detecting.
        with pytest.raises(TokenRevokedError):
            await use_case.execute(RefreshTokenCommand(raw_token))

        # The legitimate rotated token must ALSO now be revoked — reuse
        # detection revokes everything, not just the replayed one.
        rotated_token = await token_repo.get_by_token_hash(
            hash_refresh_token(first_result.refresh_token)
        )
        assert rotated_token is not None
        assert rotated_token.is_revoked is True

        stored_user = await user_repo.get_by_id(user.id)
        assert stored_user is not None
        assert stored_user.token_version == 1  # bumped, invalidating outstanding access tokens

    async def test_unknown_token_raises_token_revoked_error(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        use_case = RefreshTokenUseCase(user_repo, token_repo, _make_jwt_provider())

        with pytest.raises(TokenRevokedError):
            await use_case.execute(RefreshTokenCommand("a-token-that-was-never-issued"))
