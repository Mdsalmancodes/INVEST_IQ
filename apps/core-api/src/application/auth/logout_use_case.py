"""LogoutUseCase — Document 3 §7.4: "Logout: refresh token is deleted...
'Logout everywhere': tokenVersion on User is incremented."

Two distinct operations exposed, matching the two distinct logout modes
named in Document 3 §7.4 — a single "logout" endpoint that always did both
would make "log out this device only" impossible to offer later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.auth.repositories import RefreshTokenRepository, UserRepository
from src.domain.auth.value_objects import UserId
from src.infrastructure.security.refresh_token_generator import hash_refresh_token
from src.infrastructure.security.token_blacklist import TokenBlacklist


@dataclass(frozen=True, slots=True)
class LogoutCommand:
    raw_refresh_token: str
    access_token_jti: str = ""
    access_token_remaining_ttl_seconds: int = 0
    """Phase 8 addition — when the caller's currently-presented access
    token's jti/remaining-lifetime is known (the normal case: /logout is
    now an authenticated endpoint, see auth_router.py), that specific
    access token is blacklisted too, so it stops working immediately
    rather than remaining valid for the rest of its natural TTL. Both
    default to empty/0 so existing callers/tests that only care about
    refresh-token revocation continue to work unchanged — blacklisting a
    token is simply skipped when there is nothing to blacklist."""


class LogoutUseCase:
    """Revokes only the single refresh token presented — "log out this
    device" — and (Phase 8) blacklists the current access token's jti."""

    def __init__(
        self,
        refresh_token_repository: RefreshTokenRepository,
        token_blacklist: TokenBlacklist | None = None,
    ) -> None:
        self._refresh_token_repository = refresh_token_repository
        self._token_blacklist = token_blacklist

    async def execute(self, command: LogoutCommand) -> None:
        token_hash = hash_refresh_token(command.raw_refresh_token)
        token = await self._refresh_token_repository.get_by_token_hash(token_hash)
        if token is not None and not token.is_revoked:
            token.revoke(datetime.now(UTC))
            await self._refresh_token_repository.save(token)

        if (
            self._token_blacklist is not None
            and command.access_token_jti
            and command.access_token_remaining_ttl_seconds > 0
        ):
            await self._token_blacklist.add(
                command.access_token_jti, command.access_token_remaining_ttl_seconds
            )


@dataclass(frozen=True, slots=True)
class LogoutEverywhereCommand:
    user_id: UserId


class LogoutEverywhereUseCase:
    """Revokes all refresh tokens AND bumps token_version so outstanding
    access tokens fail their version check immediately (Document 3 §7.4)."""

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
    ) -> None:
        self._user_repository = user_repository
        self._refresh_token_repository = refresh_token_repository

    async def execute(self, command: LogoutEverywhereCommand) -> None:
        await self._refresh_token_repository.revoke_all_for_user(command.user_id, datetime.now(UTC))
        user = await self._user_repository.get_by_id(command.user_id)
        if user is not None:
            user.invalidate_all_sessions()
            await self._user_repository.save(user)
