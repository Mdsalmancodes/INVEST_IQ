"""Unit tests for JwtProvider — access token issuance, verification, kid-based
rotation overlap (Document 6 §15.4's revision)."""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest

from src.domain.auth.entities import Role
from src.domain.auth.exceptions import InvalidTokenError, TokenExpiredError
from src.domain.auth.value_objects import UserId
from src.infrastructure.security.jwt_provider import JwtProvider


def _make_provider(
    *, ttl_minutes: int = 15, previous_kid: str | None = None, previous_secret: str | None = None
) -> JwtProvider:
    return JwtProvider(
        current_kid="key-2026-07",
        current_secret="current-secret-value-at-least-32-characters-long",
        access_token_ttl_minutes=ttl_minutes,
        previous_kid=previous_kid,
        previous_secret=previous_secret,
    )


class TestIssueAndVerifyAccessToken:
    def test_round_trips_claims_correctly(self) -> None:
        provider = _make_provider()
        user_id = UserId.new()
        token = provider.issue_access_token(user_id, Role.PRO_USER, token_version=3)

        claims = provider.verify_access_token(token)

        assert claims.user_id == user_id
        assert claims.role == Role.PRO_USER
        assert claims.token_version == 3

    def test_issues_a_unique_jti_per_token(self) -> None:
        provider = _make_provider()
        user_id = UserId.new()
        token_a = provider.issue_access_token(user_id, Role.USER, token_version=0)
        token_b = provider.issue_access_token(user_id, Role.USER, token_version=0)

        claims_a = provider.verify_access_token(token_a)
        claims_b = provider.verify_access_token(token_b)

        assert claims_a.jti != claims_b.jti
        assert claims_a.jti != ""

    def test_token_header_carries_the_current_kid(self) -> None:
        provider = _make_provider()
        token = provider.issue_access_token(UserId.new(), Role.USER, token_version=0)
        header = pyjwt.get_unverified_header(token)
        assert header["kid"] == "key-2026-07"

    def test_rejects_token_with_unknown_kid(self) -> None:
        provider = _make_provider()
        # Sign a token with a completely different key/kid, simulating a
        # forged or foreign-service token.
        forged = pyjwt.encode(
            {"sub": str(UserId.new()), "role": "user", "token_version": 0, "exp": 9999999999},
            "attacker-controlled-secret",
            algorithm="HS256",
            headers={"kid": "not-a-real-key"},
        )
        with pytest.raises(InvalidTokenError):
            provider.verify_access_token(forged)

    def test_rejects_expired_token(self) -> None:
        provider = _make_provider(ttl_minutes=0)
        token = provider.issue_access_token(UserId.new(), Role.USER, token_version=0)
        time.sleep(1.1)  # ensure the exp timestamp (second-resolution) is in the past
        with pytest.raises(TokenExpiredError):
            provider.verify_access_token(token)

    def test_rejects_malformed_token(self) -> None:
        provider = _make_provider()
        with pytest.raises(InvalidTokenError):
            provider.verify_access_token("not.a.real.jwt")

    def test_accepts_a_pre_phase_8_token_with_no_jti_claim_at_all(self) -> None:
        # Simulates a token issued before the jti claim existed — must
        # still verify successfully (backward compatibility during
        # rollout), with jti simply defaulting to "".
        provider = _make_provider()
        legacy_token = pyjwt.encode(
            {
                "sub": str(UserId.new()),
                "role": "user",
                "token_version": 0,
                "iat": int(time.time()),
                "exp": int(time.time()) + 900,
            },
            "current-secret-value-at-least-32-characters-long",
            algorithm="HS256",
            headers={"kid": "key-2026-07"},
        )

        claims = provider.verify_access_token(legacy_token)

        assert claims.jti == ""


class TestKidBasedRotationOverlap:
    def test_accepts_token_signed_with_previous_key_during_overlap(self) -> None:
        # Simulates rotation: a token issued before rotation (signed with
        # what is now the "previous" key) must still verify successfully
        # during the overlap window (Document 6 §15.4).
        old_provider = _make_provider()
        old_token = old_provider.issue_access_token(UserId.new(), Role.USER, token_version=0)

        rotated_provider = JwtProvider(
            current_kid="key-2026-10",
            current_secret="new-secret-value-also-at-least-32-characters",
            access_token_ttl_minutes=15,
            previous_kid="key-2026-07",
            previous_secret="current-secret-value-at-least-32-characters-long",
        )

        claims = rotated_provider.verify_access_token(old_token)
        assert claims.token_version == 0

    def test_rejects_previous_key_token_once_overlap_window_closes(self) -> None:
        old_provider = _make_provider()
        old_token = old_provider.issue_access_token(UserId.new(), Role.USER, token_version=0)

        # No previous_kid/previous_secret configured — overlap window has closed.
        rotated_provider = JwtProvider(
            current_kid="key-2026-10",
            current_secret="new-secret-value-also-at-least-32-characters",
            access_token_ttl_minutes=15,
        )

        with pytest.raises(InvalidTokenError):
            rotated_provider.verify_access_token(old_token)
