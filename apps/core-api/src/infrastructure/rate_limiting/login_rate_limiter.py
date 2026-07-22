"""Redis-backed rate limiting for auth endpoints — Document 6 §15.2's login
rate limiting ("5 failed attempts per account per 15 minutes triggers
exponential backoff; 10 failed attempts triggers a temporary account lock")
and Document 4 §9.6's general sliding-window pattern, applied here
specifically to login attempts (redis-session instance, per Document 3 §7.7).

Uses Redis INCR + EXPIRE directly (a standard, well-understood sliding/
fixed-window counter pattern) rather than a heavier rate-limiting library,
since the actual logic needed is small and the behavior must match Document
6 §15.2's specific two-threshold (5 attempts -> backoff, 10 -> lock) policy
exactly, which a generic off-the-shelf limiter would not express cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

_FAILED_LOGIN_KEY_PREFIX = "ratelimit:login:"
_WINDOW_SECONDS = 15 * 60  # 15 minutes, per Document 6 §15.2
_BACKOFF_THRESHOLD = 5
_LOCK_THRESHOLD = 10


@dataclass(frozen=True, slots=True)
class LoginAttemptStatus:
    failed_count: int
    is_locked: bool
    requires_backoff: bool


class LoginRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, email: str) -> str:
        return f"{_FAILED_LOGIN_KEY_PREFIX}{email}"

    async def get_status(self, email: str) -> LoginAttemptStatus:
        raw = await self._redis.get(self._key(email))
        count = int(raw) if raw is not None else 0
        return LoginAttemptStatus(
            failed_count=count,
            is_locked=count >= _LOCK_THRESHOLD,
            requires_backoff=count >= _BACKOFF_THRESHOLD,
        )

    async def record_failed_attempt(self, email: str) -> LoginAttemptStatus:
        key = self._key(email)
        count = await self._redis.incr(key)
        if count == 1:
            # Only set the expiry on the first failed attempt in a window —
            # subsequent INCRs must not reset the window, or a fast-repeating
            # attacker could keep the window perpetually open.
            await self._redis.expire(key, _WINDOW_SECONDS)
        return LoginAttemptStatus(
            failed_count=count,
            is_locked=count >= _LOCK_THRESHOLD,
            requires_backoff=count >= _BACKOFF_THRESHOLD,
        )

    async def clear(self, email: str) -> None:
        """Called on successful login — resets the counter."""
        await self._redis.delete(self._key(email))

    async def get_retry_after_seconds(self, email: str) -> int:
        ttl = await self._redis.ttl(self._key(email))
        return max(int(ttl), 0)
