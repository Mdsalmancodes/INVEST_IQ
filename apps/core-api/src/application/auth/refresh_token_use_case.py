"""RefreshTokenUseCase — Document 3 §7.4: refresh token rotation with reuse
detection ("validates it against the stored hash, rotates it... refresh
token rotation prevents replay").

Reuse-detection logic: if the presented token hash matches a REVOKED token
(not just "not found"), that is evidence the token was already used once and
is being replayed — e.g. an attacker who stole an old refresh token from a
compromised device. Per Document 3 §7.4 revision (Doc 6 §15.1's security
posture), this triggers revoking ALL of that user's sessions, not just
rejecting the one request — the same "force logout everywhere" response as
a detected compromise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.domain.auth.entities import RefreshToken
from src.domain.auth.exceptions import TokenExpiredError, TokenRevokedError, UserNotFoundError
from src.domain.auth.repositories import RefreshTokenRepository, UserRepository
from src.domain.auth.value_objects import UserId
from src.infrastructure.security.jwt_provider import JwtProvider
from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)

_REFRESH_TOKEN_TTL_DAYS = 30


@dataclass(frozen=True, slots=True)
class RefreshTokenCommand:
    raw_refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshTokenResult:
    access_token: str
    refresh_token: str


class RefreshTokenUseCase:
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        jwt_provider: JwtProvider,
    ) -> None:
        self._user_repository = user_repository
        self._refresh_token_repository = refresh_token_repository
        self._jwt_provider = jwt_provider

    async def execute(self, command: RefreshTokenCommand) -> RefreshTokenResult:
        token_hash = hash_refresh_token(command.raw_refresh_token)
        existing_token = await self._refresh_token_repository.get_by_token_hash(token_hash)

        if existing_token is None:
            raise TokenRevokedError("Refresh token not recognized")

        if existing_token.is_revoked:
            # Reuse of an already-rotated/revoked token — treat as a
            # detected compromise and force logout everywhere (Document 3 §7.4).
            await self._refresh_token_repository.revoke_all_for_user(
                existing_token.user_id, datetime.now(UTC)
            )
            user = await self._user_repository.get_by_id(existing_token.user_id)
            if user is not None:
                user.invalidate_all_sessions()
                await self._user_repository.save(user)
            raise TokenRevokedError(
                "Refresh token has already been used — all sessions have been revoked"
            )

        now = datetime.now(UTC)
        if existing_token.is_expired(now):
            raise TokenExpiredError("Refresh token has expired")

        user = await self._user_repository.get_by_id(existing_token.user_id)
        if user is None:
            raise UserNotFoundError("User for this refresh token no longer exists")

        # Rotation: revoke the presented token, issue a brand new one.
        existing_token.revoke(now)
        await self._refresh_token_repository.save(existing_token)

        new_raw_token = generate_refresh_token()
        new_token = RefreshToken(
            id=UserId.new(),
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw_token),
            expires_at=now + timedelta(days=_REFRESH_TOKEN_TTL_DAYS),
            created_at=now,
        )
        await self._refresh_token_repository.save(new_token)

        access_token = self._jwt_provider.issue_access_token(user.id, user.role, user.token_version)

        return RefreshTokenResult(access_token=access_token, refresh_token=new_raw_token)
