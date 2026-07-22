"""Unit tests for RegisterUseCase."""

from __future__ import annotations

import pytest

from src.application.auth.register_use_case import RegisterCommand, RegisterUseCase
from src.domain.auth.exceptions import UserAlreadyExistsError, WeakPasswordError
from src.infrastructure.security.password_hasher import Argon2PasswordHasher
from tests.unit.application.fakes import FakeUserRepository


def _make_use_case() -> tuple[RegisterUseCase, FakeUserRepository]:
    repo = FakeUserRepository()
    return RegisterUseCase(repo, Argon2PasswordHasher()), repo


class TestRegisterUseCase:
    async def test_registers_a_new_user_successfully(self) -> None:
        use_case, repo = _make_use_case()
        command = RegisterCommand(
            email="newuser@example.com",
            password="a-genuinely-strong-passphrase",
            full_name="New User",
        )

        result = await use_case.execute(command)

        stored = await repo.get_by_id(result.user_id)
        assert stored is not None
        assert stored.full_name == "New User"
        assert stored.email_verified_at is None  # verification is a separate step
        assert stored.hashed_password is not None
        assert stored.hashed_password.value.startswith("$argon2id$")

    async def test_rejects_duplicate_email(self) -> None:
        use_case, _ = _make_use_case()
        command = RegisterCommand(
            email="duplicate@example.com",
            password="a-genuinely-strong-passphrase",
            full_name="First User",
        )
        await use_case.execute(command)

        with pytest.raises(UserAlreadyExistsError):
            await use_case.execute(
                RegisterCommand(
                    email="duplicate@example.com",
                    password="a-different-strong-passphrase",
                    full_name="Second User",
                )
            )

    async def test_rejects_duplicate_email_case_insensitively(self) -> None:
        use_case, _ = _make_use_case()
        await use_case.execute(
            RegisterCommand(
                email="CaseTest@example.com",
                password="a-genuinely-strong-passphrase",
                full_name="First User",
            )
        )

        with pytest.raises(UserAlreadyExistsError):
            await use_case.execute(
                RegisterCommand(
                    email="casetest@example.com",
                    password="a-different-strong-passphrase",
                    full_name="Second User",
                )
            )

    async def test_rejects_common_password(self) -> None:
        use_case, _ = _make_use_case()
        with pytest.raises(WeakPasswordError):
            await use_case.execute(
                RegisterCommand(
                    email="user@example.com",
                    password="1234567890",  # in the blocklist AND meets the 10-char length minimum
                    full_name="Test User",
                )
            )

    async def test_strips_whitespace_from_full_name(self) -> None:
        use_case, repo = _make_use_case()
        result = await use_case.execute(
            RegisterCommand(
                email="whitespace@example.com",
                password="a-genuinely-strong-passphrase",
                full_name="  Padded Name  ",
            )
        )
        stored = await repo.get_by_id(result.user_id)
        assert stored is not None
        assert stored.full_name == "Padded Name"
