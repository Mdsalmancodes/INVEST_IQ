"""TokenBlacklist — Phase 8's Redis-backed single-access-token revocation.

Distinct from the existing token_version mechanism
(src/domain/auth/entities.py's User.invalidate_all_sessions()), which
invalidates EVERY access token for a user at once ("logout everywhere").
This blacklist lets /logout revoke exactly the one access token that was
presented, without forcing every other active session for that user to
re-authenticate — closing the gap that previously existed: logging out
only deleted the refresh token, while the still-valid access token
remained usable for the rest of its (up to 15-minute) natural lifetime.

Uses redis-session (Document 3 §7.7: "sessions/rate-limit counters") via
the EXISTING get_redis_clients().session client — never a new Redis
instance — matching LoginRateLimiter's established pattern of reusing
that exact client for this exact category of ephemeral, TTL-bounded data.
"""

from __future__ import annotations

from redis.asyncio import Redis

_BLACKLIST_KEY_PREFIX = "blacklist:access_token:"


class TokenBlacklist:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, jti: str) -> str:
        return f"{_BLACKLIST_KEY_PREFIX}{jti}"

    async def add(self, jti: str, ttl_seconds: int) -> None:
        """Blacklists `jti` for exactly `ttl_seconds` — should always be
        set to the token's own REMAINING lifetime (not the full original
        TTL), so the blacklist entry naturally expires at the same moment
        the token itself would have expired anyway, never growing Redis
        memory usage for tokens that are already dead."""
        if ttl_seconds <= 0:
            return
        await self._redis.set(self._key(jti), "1", ex=ttl_seconds)

    async def is_blacklisted(self, jti: str) -> bool:
        if not jti:
            # A token with no jti claim at all (issued before this Phase 8
            # change — see jwt_provider.py's verify_access_token docstring)
            # can never have been individually blacklisted; treating an
            # empty jti as "not blacklisted" is correct, not a bypass.
            return False
        exists_count = await self._redis.exists(self._key(jti))
        return bool(exists_count > 0)
