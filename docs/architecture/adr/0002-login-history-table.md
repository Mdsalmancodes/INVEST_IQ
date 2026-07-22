# ADR-0002: Add `login_history` Table for Login History & Device Tracking

**Status:** Accepted (founder ratification, 2026-07-22)
**Date:** 2026-07-22
**Supersedes/amends:** Document 3 (`03-backend-architecture-database-design.md`) §8.1 — adds a new table not present in the original frozen schema. Does not modify or remove any existing table.

## Context

Phase 2's explicit requirements (founder instruction) include "Login history" and "Device tracking" as backend features. The frozen architecture's Identity & Access schema (Document 3 §8.1) defines `users`, `oauth_accounts`, `refresh_tokens`, and `audit_logs`, but has no dedicated table for per-login-attempt history (timestamp, IP, user agent/device fingerprint, success/failure) queryable by the user themselves (e.g., a "recent logins" security page) — `audit_logs` is a platform-wide, admin-oriented security log (Document 3 §7.6/§15.6 framing: "admin-only read"), not designed as a user-facing feature.

This is a genuine gap between an explicit new requirement and the frozen schema, not a redesign of anything existing — per the founder's standing rule ("if a feature is too large... implement a production-quality MVP that preserves the same architecture" and "if simplification becomes necessary, create an ADR first"), this ADR proposes the smallest correct extension rather than either (a) silently adding the table without a record, or (b) overloading `audit_logs` for a purpose it wasn't designed for.

## Decision

Add a new table, purely additive to the existing schema:

```sql
CREATE TABLE login_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip_address      INET,
    user_agent      TEXT,
    device_label    TEXT,            -- derived from user_agent (e.g. "Chrome on Windows"), for display
    success         BOOLEAN NOT NULL,
    failure_reason  TEXT,             -- NULL on success; 'invalid_credentials' | 'account_locked' | etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_login_history_user_time ON login_history(user_id, created_at DESC);
```

- **Relationship to `audit_logs`:** `audit_logs` continues to record the same login events platform-wide (per Document 3 §7.6/§15.6, admin-facing, long-retention security trail). `login_history` is a **user-facing derived view** with a schema shaped for that specific UI need (device label, success/failure reason surfaced directly) — both are written on every login attempt from the same application-layer use case (`LoginUseCase`), not duplicated logic, just two repositories called from one place.
- **Device tracking scope for Phase 2 (MVP, explicitly not the full future scope):** `device_label` is derived via simple user-agent parsing (browser + OS), not a persistent device-fingerprint/trusted-device system (no device registration, no "remember this device" flow, no push-based new-device alerts). This matches the founder's own stated principle: implement a production-quality MVP now, with a clear upgrade path — a future `devices` table (fingerprint hash, trusted flag, last-seen) can be added later without touching this table's shape, since `login_history.device_label` would simply start being populated by that richer system instead of naive UA parsing.

## Consequences

- **Easier:** the frontend's "recent logins/security" page has a clean, purpose-built read model instead of querying/reshaping `audit_logs`.
- **Given up (for now):** no trusted-device registry, no anomaly detection on new-device logins — explicitly deferred, not silently dropped; noted above as the upgrade path.
- **Reversible:** yes — this table can be extended (new nullable columns) or have its population logic upgraded without a breaking migration.
- **No existing frozen-architecture table is modified.**

## Alternatives Considered

- **Overload `audit_logs` with a `type='login'` filter for this purpose.** Rejected: `audit_logs` is explicitly framed as admin-only/security-review-oriented in Document 3 §15.6 ("even platform engineers query this through a controlled admin endpoint, not raw DB access") — building a user-self-service feature on top of that access pattern would mean either weakening `audit_logs`'s access control or building an inconsistent parallel access path. A dedicated table keeps both concerns clean.
- **Skip device tracking/login history entirely for Phase 2, defer to a later phase.** Rejected: explicitly requested by the founder for this phase; deferring would contradict "do not scaffold, actually implement."
