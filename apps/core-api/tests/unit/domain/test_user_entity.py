"""Unit tests for the User entity's business rules (Document 3 §3.4's
aggregate design rules — invariants enforced by the entity, not scattered
across use cases)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.auth.entities import Role, User
from src.domain.auth.exceptions import EmailNotVerifiedError
from src.domain.auth.value_objects import Email, HashedPassword, UserId


def _make_user(*, email_verified: bool = True) -> User:
    now = datetime.now(UTC)
    return User(
        id=UserId.new(),
        email=Email("user@example.com"),
        hashed_password=HashedPassword("argon2$fakehash"),
        full_name="Test User",
        role=Role.USER,
        token_version=0,
        email_verified_at=now if email_verified else None,
        created_at=now,
        updated_at=now,
    )


class TestUserEmailVerification:
    def test_is_email_verified_true_when_timestamp_present(self) -> None:
        assert _make_user(email_verified=True).is_email_verified is True

    def test_is_email_verified_false_when_timestamp_absent(self) -> None:
        assert _make_user(email_verified=False).is_email_verified is False

    def test_ensure_can_login_with_password_raises_when_unverified(self) -> None:
        user = _make_user(email_verified=False)
        with pytest.raises(EmailNotVerifiedError):
            user.ensure_can_login_with_password()

    def test_ensure_can_login_with_password_passes_when_verified(self) -> None:
        user = _make_user(email_verified=True)
        user.ensure_can_login_with_password()  # should not raise


class TestUserOAuthOnly:
    def test_is_oauth_only_true_when_no_hashed_password(self) -> None:
        user = _make_user()
        user.hashed_password = None
        assert user.is_oauth_only is True

    def test_is_oauth_only_false_when_hashed_password_present(self) -> None:
        assert _make_user().is_oauth_only is False


class TestUserSessionInvalidation:
    def test_invalidate_all_sessions_increments_token_version(self) -> None:
        user = _make_user()
        assert user.token_version == 0
        user.invalidate_all_sessions()
        assert user.token_version == 1
        user.invalidate_all_sessions()
        assert user.token_version == 2

    def test_change_password_updates_hash_and_invalidates_sessions(self) -> None:
        user = _make_user()
        new_hash = HashedPassword("argon2$newhash")
        user.change_password(new_hash)
        assert user.hashed_password == new_hash
        assert user.token_version == 1  # security-sensitive event bumps version


class TestUserEmailVerificationMutation:
    def test_mark_email_verified_sets_timestamp(self) -> None:
        user = _make_user(email_verified=False)
        assert user.email_verified_at is None
        now = datetime.now(UTC)
        user.mark_email_verified(now)
        assert user.email_verified_at == now
