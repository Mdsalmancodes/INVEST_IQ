"""RegisterUseCase — Document 3 §7.4 registration flow (credential validation,
email uniqueness, Argon2 hashing) + Document 6 §15.2 (common-password
blocklist check, applied here since it needs an external wordlist resource
the domain value object cannot depend on).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.auth.entities import Role, User
from src.domain.auth.exceptions import UserAlreadyExistsError, WeakPasswordError
from src.domain.auth.repositories import UserRepository
from src.domain.auth.value_objects import Email, PlaintextPassword, UserId
from src.infrastructure.security.common_password_blocklist import is_common_password
from src.infrastructure.security.password_hasher import Argon2PasswordHasher


@dataclass(frozen=True, slots=True)
class RegisterCommand:
    email: str
    password: str
    full_name: str


@dataclass(frozen=True, slots=True)
class RegisterResult:
    user_id: UserId
    email: Email


class RegisterUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: Argon2PasswordHasher,
    ) -> None:
        self._user_repository = user_repository
        self._password_hasher = password_hasher

    async def execute(self, command: RegisterCommand) -> RegisterResult:
        email = Email(command.email)
        password = PlaintextPassword(command.password)

        if is_common_password(password.value):
            raise WeakPasswordError(
                "This password is too common. Please choose a stronger password."
            )

        if await self._user_repository.exists_with_email(email):
            raise UserAlreadyExistsError(f"An account with email '{email}' already exists")

        now = datetime.now(UTC)
        user = User(
            id=UserId.new(),
            email=email,
            hashed_password=self._password_hasher.hash(password),
            full_name=command.full_name.strip(),
            role=Role.USER,
            token_version=0,
            email_verified_at=None,  # verified via VerifyEmailUseCase
            created_at=now,
            updated_at=now,
        )
        await self._user_repository.save(user)

        return RegisterResult(user_id=user.id, email=user.email)
