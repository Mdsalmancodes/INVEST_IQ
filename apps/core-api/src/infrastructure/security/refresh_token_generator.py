"""Refresh token generation and hashing — Document 3 §7.4: "Refresh Token
(opaque random string, stored hashed in Postgres + Redis with matching TTL,
30 day expiry, rotation on each use)".

Uses `secrets` (stdlib, cryptographically secure) for generation and
`hashlib.sha256` for hashing — a refresh token is a high-entropy random
value (not a low-entropy password), so a fast cryptographic hash is
appropriate here (unlike passwords, which need Argon2's deliberate slowness
against brute-force guessing of low-entropy human-chosen input).
"""

from __future__ import annotations

import hashlib
import secrets

_TOKEN_BYTES = 32  # 256 bits of entropy


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
