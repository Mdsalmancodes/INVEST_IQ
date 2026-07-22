"""Domain entities for the auth bounded context.

Per Document 3 §8.1 (users, oauth_accounts, refresh_tokens, audit_logs) and
ADR-0002 (login_history). These are plain dataclasses with behavior — not
Pydantic models (Document 8 §20.2) — representing the actual business rules
(e.g., "logging out everywhere" bumps token_version; a refresh token can only
be rotated once before its replacement supersedes it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.auth.exceptions import EmailNotVerifiedError
from src.domain.auth.value_objects import Email, HashedPassword, UserId


class Role(str, Enum):
    USER = "user"
    PRO_USER = "pro_user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass(slots=True)
class User:
    """Aggregate root for the Identity & Access context (Document 3 DDD §3.1).

    Invariants enforced here, not scattered across use cases:
    - token_version only ever increases (never reset), so a stale JWT can
      never become valid again by coincidence.
    - Only a verified email may authenticate via password login (OAuth-only
      accounts, hashed_password is None, bypass this — Document 3 §8.1).
    """

    id: UserId
    email: Email
    hashed_password: HashedPassword | None
    full_name: str
    role: Role
    token_version: int
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime
    risk_profile: RiskProfile | None = None

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_oauth_only(self) -> bool:
        return self.hashed_password is None

    def ensure_can_login_with_password(self) -> None:
        if not self.is_email_verified:
            raise EmailNotVerifiedError("Email must be verified before password login is permitted")

    def invalidate_all_sessions(self) -> None:
        """Bumps token_version — every previously issued access token fails
        its version check on next use (Document 3 §7.4 'logout everywhere').
        """
        self.token_version += 1

    def mark_email_verified(self, at: datetime) -> None:
        self.email_verified_at = at

    def change_password(self, new_hashed_password: HashedPassword) -> None:
        self.hashed_password = new_hashed_password
        # Changing password is a security-sensitive event — invalidate every
        # other outstanding session, matching Document 6 §15.6's audit-logged
        # security actions list ("password change" is explicitly named there).
        self.invalidate_all_sessions()


@dataclass(slots=True)
class RefreshToken:
    """Represents one issued refresh token (Document 3 §8.1 refresh_tokens
    table). The raw token value is never stored — only its hash
    (token_hash) — so a leaked database dump alone can't be used to forge
    sessions (Document 3 §7.4).
    """

    id: UserId  # reusing UserId's UUID wrapper — it's a generic UUID VO, not user-specific
    user_id: UserId
    token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def revoke(self, at: datetime) -> None:
        self.revoked_at = at


@dataclass(slots=True)
class LoginHistoryEntry:
    """Per ADR-0002 — user-facing login history/device tracking record."""

    id: UserId
    user_id: UserId
    ip_address: str | None
    user_agent: str | None
    device_label: str | None
    success: bool
    failure_reason: str | None
    created_at: datetime


@dataclass(slots=True)
class AuditLogEntry:
    """Platform-wide security audit trail (Document 3 §8.1 audit_logs,
    Document 6 §15.6). Admin-facing, distinct purpose from LoginHistoryEntry
    (ADR-0002) even though both may be written for the same login event.
    """

    id: UserId
    user_id: UserId | None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
