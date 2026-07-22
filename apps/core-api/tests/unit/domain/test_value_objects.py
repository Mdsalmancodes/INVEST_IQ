"""Unit tests for auth value objects — Document 6 §16.2's domain-layer
coverage target (95%+, "no excuse for gaps" since it's pure logic)."""

from __future__ import annotations

import pytest

from src.domain.auth.exceptions import InvalidEmailError, InvalidPasswordError
from src.domain.auth.value_objects import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Email,
    PlaintextPassword,
    UserId,
)


class TestUserId:
    def test_new_generates_a_valid_uuid(self) -> None:
        user_id = UserId.new()
        assert user_id.value is not None

    def test_two_new_ids_are_distinct(self) -> None:
        assert UserId.new() != UserId.new()

    def test_from_string_round_trips(self) -> None:
        original = UserId.new()
        reconstructed = UserId.from_string(str(original))
        assert original == reconstructed

    def test_from_string_rejects_malformed_input(self) -> None:
        with pytest.raises(ValueError):
            UserId.from_string("not-a-uuid")


class TestEmail:
    @pytest.mark.parametrize(
        "raw",
        ["user@example.com", "USER@EXAMPLE.COM", "  user@example.com  "],
    )
    def test_normalizes_to_lowercase_and_trims(self, raw: str) -> None:
        assert Email(raw).value == "user@example.com"

    @pytest.mark.parametrize(
        "raw",
        ["not-an-email", "missing-domain@", "@missing-local.com", "no spaces allowed@x.com"],
    )
    def test_rejects_invalid_format(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            Email(raw)

    def test_two_emails_differing_only_by_case_are_equal(self) -> None:
        assert Email("User@Example.com") == Email("user@example.com")

    def test_str_returns_normalized_value(self) -> None:
        assert str(Email("User@Example.com")) == "user@example.com"


class TestPlaintextPassword:
    def test_accepts_password_at_minimum_length(self) -> None:
        password = "a" * MIN_PASSWORD_LENGTH
        assert PlaintextPassword(password).value == password

    def test_accepts_password_at_maximum_length(self) -> None:
        password = "a" * MAX_PASSWORD_LENGTH
        assert PlaintextPassword(password).value == password

    def test_rejects_password_below_minimum_length(self) -> None:
        with pytest.raises(InvalidPasswordError):
            PlaintextPassword("a" * (MIN_PASSWORD_LENGTH - 1))

    def test_rejects_password_above_maximum_length(self) -> None:
        with pytest.raises(InvalidPasswordError):
            PlaintextPassword("a" * (MAX_PASSWORD_LENGTH + 1))

    def test_repr_never_leaks_the_plaintext_value(self) -> None:
        password = PlaintextPassword("supersecretvalue123")
        assert "supersecretvalue123" not in repr(password)
        assert repr(password) == "PlaintextPassword('[REDACTED]')"
