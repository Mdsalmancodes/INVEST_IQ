"""Unit tests for the RefreshToken entity — Document 3 §7.4's rotation/
revocation invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.domain.auth.entities import RefreshToken
from src.domain.auth.value_objects import UserId


def _make_token(*, expires_in: timedelta, revoked: bool = False) -> RefreshToken:
    now = datetime.now(UTC)
    return RefreshToken(
        id=UserId.new(),
        user_id=UserId.new(),
        token_hash="hashed-token-value",
        expires_at=now + expires_in,
        created_at=now,
        revoked_at=now if revoked else None,
    )


class TestRefreshTokenExpiry:
    def test_is_expired_false_before_expiry(self) -> None:
        token = _make_token(expires_in=timedelta(days=1))
        assert token.is_expired(datetime.now(UTC)) is False

    def test_is_expired_true_after_expiry(self) -> None:
        token = _make_token(expires_in=timedelta(seconds=-1))
        assert token.is_expired(datetime.now(UTC)) is True

    def test_is_expired_true_at_exact_expiry_boundary(self) -> None:
        token = _make_token(expires_in=timedelta(seconds=0))
        # `now` passed in is at-or-after expires_at by the time this runs
        assert token.is_expired(token.expires_at) is True


class TestRefreshTokenRevocation:
    def test_is_revoked_false_by_default(self) -> None:
        token = _make_token(expires_in=timedelta(days=1))
        assert token.is_revoked is False

    def test_revoke_sets_revoked_at(self) -> None:
        token = _make_token(expires_in=timedelta(days=1))
        now = datetime.now(UTC)
        token.revoke(now)
        assert token.is_revoked is True
        assert token.revoked_at == now
