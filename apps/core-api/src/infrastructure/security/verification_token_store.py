"""Single-purpose token generation for email verification and password
reset links — same opaque-token-plus-hash pattern as refresh tokens
(Document 3 §7.4), but stored in Redis (redis-session, Document 3 §7.7)
rather than Postgres, since these are short-lived (hours, not 30 days) and
don't need the durability/audit properties a Postgres row provides.

Reuses the same generation/hashing primitives as refresh tokens
(src.infrastructure.security.refresh_token_generator) since the security
properties required are identical (high-entropy opaque token, hash stored
not the raw value) — no need for a second, parallel implementation of the
same primitive.
"""

from __future__ import annotations

from redis.asyncio import Redis

from src.infrastructure.security.refresh_token_generator import (
    generate_refresh_token,
    hash_refresh_token,
)

_EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60  # 24 hours
_PASSWORD_RESET_TTL_SECONDS = 60 * 60  # 1 hour — shorter than email verification,
# since a password reset link grants a more sensitive capability


class VerificationTokenStore:
    """Generic Redis-backed store for {purpose}:{token_hash} -> user_id."""

    def __init__(self, redis: Redis, *, key_prefix: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def _key(self, token_hash: str) -> str:
        return f"{self._key_prefix}:{token_hash}"

    async def issue(self, user_id: str) -> str:
        raw_token = generate_refresh_token()
        token_hash = hash_refresh_token(raw_token)
        await self._redis.set(self._key(token_hash), user_id, ex=self._ttl_seconds)
        return raw_token

    async def consume(self, raw_token: str) -> str | None:
        """Looks up and DELETES the token atomically-enough for this use
        case (single-use semantics — a verification/reset link must not be
        usable twice). Returns the associated user_id, or None if the token
        is unknown/expired/already consumed."""
        token_hash = hash_refresh_token(raw_token)
        key = self._key(token_hash)
        user_id = await self._redis.get(key)
        if user_id is None:
            return None
        await self._redis.delete(key)
        return str(user_id)


def email_verification_store(redis: Redis) -> VerificationTokenStore:
    return VerificationTokenStore(
        redis, key_prefix="verify_email", ttl_seconds=_EMAIL_VERIFICATION_TTL_SECONDS
    )


def password_reset_store(redis: Redis) -> VerificationTokenStore:
    return VerificationTokenStore(
        redis, key_prefix="reset_password", ttl_seconds=_PASSWORD_RESET_TTL_SECONDS
    )
