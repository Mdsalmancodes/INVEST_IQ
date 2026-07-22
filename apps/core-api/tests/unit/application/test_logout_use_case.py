"""Unit tests for LogoutUseCase and LogoutEverywhereUseCase."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.application.auth.logout_use_case import (
    LogoutCommand,
    LogoutEverywhereCommand,
    LogoutEverywhereUseCase,
    LogoutUseCase,
)
from src.domain.auth.entities import RefreshToken, Role, User
from src.domain.auth.value_objects import Email, UserId
from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)
from tests.unit.application.fakes import FakeRefreshTokenRepository, FakeUserRepository


async def _make_user_with_two_tokens(
    user_repo: FakeUserRepository, token_repo: FakeRefreshTokenRepository
) -> tuple[User, str, str]:
    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email("logout-test@example.com"),
        hashed_password=None,
        full_name="Logout Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    await user_repo.save(user)

    raw_token_a = generate_refresh_token()
    raw_token_b = generate_refresh_token()
    for raw in (raw_token_a, raw_token_b):
        await token_repo.save(
            RefreshToken(
                id=UserId.new(),
                user_id=user.id,
                token_hash=hash_refresh_token(raw),
                expires_at=now + timedelta(days=30),
                created_at=now,
            )
        )
    return user, raw_token_a, raw_token_b


class TestLogoutUseCase:
    async def test_revokes_only_the_presented_token(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        _, token_a, token_b = await _make_user_with_two_tokens(user_repo, token_repo)
        use_case = LogoutUseCase(token_repo)

        await use_case.execute(LogoutCommand(token_a))

        stored_a = await token_repo.get_by_token_hash(hash_refresh_token(token_a))
        stored_b = await token_repo.get_by_token_hash(hash_refresh_token(token_b))
        assert stored_a is not None and stored_a.is_revoked is True
        assert stored_b is not None and stored_b.is_revoked is False

    async def test_logging_out_an_unknown_token_does_not_raise(self) -> None:
        token_repo = FakeRefreshTokenRepository()
        use_case = LogoutUseCase(token_repo)
        await use_case.execute(LogoutCommand("never-issued-token"))  # should not raise


class TestLogoutEverywhereUseCase:
    async def test_revokes_all_tokens_and_bumps_token_version(self) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        user, token_a, token_b = await _make_user_with_two_tokens(user_repo, token_repo)
        use_case = LogoutEverywhereUseCase(user_repo, token_repo)

        await use_case.execute(LogoutEverywhereCommand(user.id))

        stored_a = await token_repo.get_by_token_hash(hash_refresh_token(token_a))
        stored_b = await token_repo.get_by_token_hash(hash_refresh_token(token_b))
        assert stored_a is not None and stored_a.is_revoked is True
        assert stored_b is not None and stored_b.is_revoked is True

        stored_user = await user_repo.get_by_id(user.id)
        assert stored_user is not None
        assert stored_user.token_version == 1
