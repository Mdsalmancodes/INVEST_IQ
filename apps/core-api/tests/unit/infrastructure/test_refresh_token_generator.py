"""Unit tests for refresh token generation/hashing."""

from __future__ import annotations

from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)


class TestRefreshTokenGeneration:
    def test_generates_a_url_safe_string(self) -> None:
        token = generate_refresh_token()
        assert isinstance(token, str)
        assert len(token) > 32

    def test_two_generated_tokens_are_distinct(self) -> None:
        assert generate_refresh_token() != generate_refresh_token()


class TestRefreshTokenHashing:
    def test_hash_is_deterministic(self) -> None:
        token = generate_refresh_token()
        assert hash_refresh_token(token) == hash_refresh_token(token)

    def test_different_tokens_hash_differently(self) -> None:
        token_a = generate_refresh_token()
        token_b = generate_refresh_token()
        assert hash_refresh_token(token_a) != hash_refresh_token(token_b)

    def test_hash_does_not_contain_the_raw_token(self) -> None:
        token = generate_refresh_token()
        assert token not in hash_refresh_token(token)
