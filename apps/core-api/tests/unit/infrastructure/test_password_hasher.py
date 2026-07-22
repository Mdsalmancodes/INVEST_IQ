"""Unit tests for Argon2PasswordHasher — genuinely security-critical, so
tested directly rather than relying only on integration tests later."""

from __future__ import annotations

from src.domain.auth.value_objects import PlaintextPassword
from src.infrastructure.security.password_hasher import Argon2PasswordHasher


class TestArgon2PasswordHasher:
    def test_hash_produces_argon2_formatted_string(self) -> None:
        hasher = Argon2PasswordHasher()
        hashed = hasher.hash(PlaintextPassword("correcthorsebattery"))
        assert hashed.value.startswith("$argon2id$")

    def test_verify_succeeds_for_correct_password(self) -> None:
        hasher = Argon2PasswordHasher()
        password = PlaintextPassword("correcthorsebattery")
        hashed = hasher.hash(password)
        assert hasher.verify(password, hashed) is True

    def test_verify_fails_for_incorrect_password(self) -> None:
        hasher = Argon2PasswordHasher()
        hashed = hasher.hash(PlaintextPassword("correcthorsebattery"))
        assert hasher.verify(PlaintextPassword("wrongpasswordvalue"), hashed) is False

    def test_two_hashes_of_the_same_password_are_different(self) -> None:
        # Argon2 includes a random salt per hash — this is what prevents
        # identical passwords from producing identical stored hashes
        # (rainbow-table resistance).
        hasher = Argon2PasswordHasher()
        password = PlaintextPassword("correcthorsebattery")
        assert hasher.hash(password).value != hasher.hash(password).value

    def test_needs_rehash_false_for_freshly_hashed_password(self) -> None:
        hasher = Argon2PasswordHasher()
        hashed = hasher.hash(PlaintextPassword("correcthorsebattery"))
        assert hasher.needs_rehash(hashed) is False
