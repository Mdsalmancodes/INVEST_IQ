"""Unit tests for RequestEmailVerificationUseCase and VerifyEmailUseCase."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.application.auth.verify_email_use_case import (
    RequestEmailVerificationCommand,
    RequestEmailVerificationUseCase,
    VerifyEmailCommand,
    VerifyEmailUseCase,
)
from src.domain.auth.entities import Role, User
from src.domain.auth.exceptions import InvalidTokenError
from src.domain.auth.value_objects import Email, UserId
from tests.unit.application.fake_token_store import FakeVerificationTokenStore
from tests.unit.application.fakes import FakeUserRepository


async def _make_unverified_user(user_repo: FakeUserRepository) -> User:
    now = datetime.now(UTC)
    user = User(
        id=UserId.new(),
        email=Email("unverified@example.com"),
        hashed_password=None,
        full_name="Unverified User",
        role=Role.USER,
        token_version=0,
        email_verified_at=None,
        created_at=now,
        updated_at=now,
    )
    await user_repo.save(user)
    return user


class TestRequestEmailVerification:
    async def test_issues_a_token_for_an_unverified_user(self) -> None:
        user_repo = FakeUserRepository()
        user = await _make_unverified_user(user_repo)
        use_case = RequestEmailVerificationUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(RequestEmailVerificationCommand(str(user.email)))

        assert result is not None
        assert result.user_id == user.id
        assert result.raw_token

    async def test_returns_none_for_unknown_email(self) -> None:
        user_repo = FakeUserRepository()
        use_case = RequestEmailVerificationUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(
            RequestEmailVerificationCommand("nobody@example.com")
        )

        assert result is None

    async def test_returns_none_if_already_verified(self) -> None:
        user_repo = FakeUserRepository()
        user = await _make_unverified_user(user_repo)
        user.mark_email_verified(datetime.now(UTC))
        await user_repo.save(user)
        use_case = RequestEmailVerificationUseCase(user_repo, FakeVerificationTokenStore())

        result = await use_case.execute(RequestEmailVerificationCommand(str(user.email)))

        assert result is None


class TestVerifyEmail:
    async def test_marks_email_verified_with_a_valid_token(self) -> None:
        user_repo = FakeUserRepository()
        user = await _make_unverified_user(user_repo)
        token_store = FakeVerificationTokenStore()
        request_use_case = RequestEmailVerificationUseCase(user_repo, token_store)
        verify_use_case = VerifyEmailUseCase(user_repo, token_store)

        issued = await request_use_case.execute(
            RequestEmailVerificationCommand(str(user.email))
        )
        assert issued is not None

        verified_user_id = await verify_use_case.execute(VerifyEmailCommand(issued.raw_token))

        assert verified_user_id == user.id
        stored = await user_repo.get_by_id(user.id)
        assert stored is not None
        assert stored.is_email_verified is True

    async def test_rejects_invalid_token(self) -> None:
        user_repo = FakeUserRepository()
        use_case = VerifyEmailUseCase(user_repo, FakeVerificationTokenStore())

        with pytest.raises(InvalidTokenError):
            await use_case.execute(VerifyEmailCommand("never-issued-token"))

    async def test_token_cannot_be_used_twice(self) -> None:
        user_repo = FakeUserRepository()
        user = await _make_unverified_user(user_repo)
        token_store = FakeVerificationTokenStore()
        request_use_case = RequestEmailVerificationUseCase(user_repo, token_store)
        verify_use_case = VerifyEmailUseCase(user_repo, token_store)

        issued = await request_use_case.execute(
            RequestEmailVerificationCommand(str(user.email))
        )
        assert issued is not None
        await verify_use_case.execute(VerifyEmailCommand(issued.raw_token))

        with pytest.raises(InvalidTokenError):
            await verify_use_case.execute(VerifyEmailCommand(issued.raw_token))
