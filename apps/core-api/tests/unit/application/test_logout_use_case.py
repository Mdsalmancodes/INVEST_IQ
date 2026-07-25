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


class FakeTokenBlacklist:
    def __init__(self) -> None:
        self.added: list[tuple[str, int]] = []

    async def add(self, jti: str, ttl_seconds: int) -> None:
        self.added.append((jti, ttl_seconds))

    async def is_blacklisted(self, jti: str) -> bool:
        return any(added_jti == jti for added_jti, _ in self.added)


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

    async def test_blacklists_the_current_access_token_when_jti_and_ttl_are_provided(
        self,
    ) -> None:
        user_repo, token_repo = FakeUserRepository(), FakeRefreshTokenRepository()
        _, token_a, _ = await _make_user_with_two_tokens(user_repo, token_repo)
        blacklist = FakeTokenBlacklist()
        use_case = LogoutUseCase(token_repo, blacklist)

        await use_case.execute(
            LogoutCommand(
                raw_refresh_token=token_a,
                access_token_jti="some-jti",
                access_token_remaining_ttl_seconds=300,
            )
        )

        assert blacklist.added == [("some-jti", 300)]

    async def test_does_not_blacklist_anything_when_jti_is_not_provided(self) -> None:
        # Matches every pre-Phase-8 call site/test that only cares about
        # refresh-token revocation — nothing should be blacklisted when
        # there is no jti to blacklist.
        token_repo = FakeRefreshTokenRepository()
        blacklist = FakeTokenBlacklist()
        use_case = LogoutUseCase(token_repo, blacklist)

        await use_case.execute(LogoutCommand(raw_refresh_token="never-issued-token"))

        assert blacklist.added == []

    async def test_works_without_a_token_blacklist_injected_at_all(self) -> None:
        # Backward-compatible constructor default (token_blacklist=None) —
        # existing callers that never pass one continue to work.
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
