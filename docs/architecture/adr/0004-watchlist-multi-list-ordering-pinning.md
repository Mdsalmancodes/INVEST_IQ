# ADR-0004: Extend `watchlists`/`watchlist_items` for Multi-Watchlist, Ordering, Pinning, and Default-Watchlist Support

**Status:** Accepted (founder ratification, 2026-07-22)
**Date:** 2026-07-22
**Supersedes/amends:** Document 3 (`03-backend-architecture-database-design.md`) §8.1 — the `watchlists`/`watchlist_items` tables; Document 4 (`04-api-design-ai-ml-pipeline.md`) — the Watchlist endpoint catalog.

## Context

Phase 5's explicit founder requirements are: multiple watchlists per user, full CRUD (create/rename/delete watchlists, not just list+add-item+remove-item), a default watchlist per user, custom item ordering preserved, pinning favorite symbols, and date-added tracking.

The frozen schema (Document 3 §8.1) is:

```sql
CREATE TABLE watchlists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL DEFAULT 'My Watchlist',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE watchlist_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id    UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(watchlist_id, instrument_id)
);
```

This is the same category of gap as ADR-0002/ADR-0003: an explicit new requirement the frozen schema does not yet fully accommodate. Already supported without any change: multiple watchlists per user (no uniqueness constraint on `user_id` alone — a user can already have many rows), duplicate-symbol prevention within one watchlist (`UNIQUE(watchlist_id, instrument_id)` already exists), and date-added tracking (`added_at` already exists). **Not supported by the frozen schema:**

1. **Renaming a watchlist** — `name` exists but there is no `updated_at` to record when it was last changed (every other frozen table with a mutable field carries one, e.g. `portfolios`, `holdings` — this is an oversight, not a deliberate omission).
2. **Default watchlist per user** — no column distinguishes which of a user's watchlists (if any) is the default one shown on first login/dashboard load.
3. **Custom item ordering** — no column records a user-chosen display order; `added_at` only gives insertion order, which the founder's requirement ("preserve custom ordering") explicitly distinguishes from.
4. **Pinning favorite symbols** — no boolean exists to mark a watchlist item as pinned/favorited for priority display.
5. **Full CRUD surface** — Document 4's catalog only lists `GET /watchlists`, `POST /watchlists/{id}/items`, `DELETE /watchlists/{id}/items/{itemId}`. There is no `POST /watchlists` (create), `PATCH /watchlists/{id}` (rename), `DELETE /watchlists/{id}` (delete a whole watchlist), or `PATCH /watchlists/{id}/items/{itemId}` (pin/reorder) — all explicitly required by the founder's Phase 5 instruction.

## Decision

Extend both tables additively — no existing column removed or retyped:

```sql
ALTER TABLE watchlists ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT false;
    -- Exactly one row per user_id may have is_default = true, enforced by a
    -- partial unique index (see below), not application-only logic — the
    -- same defense-in-depth pattern the frozen schema already uses for
    -- idx_instruments_symbol_global (Document 3 §8.1) and
    -- idx_paper_orders_idempotency.
ALTER TABLE watchlists ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    -- Bumped on rename, via the same shared set_updated_at() trigger
    -- function already defined once in Document 3 §8.1's preamble and
    -- reused by paper_orders/portfolios/holdings — no new trigger function
    -- needed, only a new CREATE TRIGGER binding it to this table.

CREATE UNIQUE INDEX idx_watchlists_user_default ON watchlists(user_id) WHERE is_default = true;
    -- Enforces "at most one default watchlist per user" at the database
    -- level. Every user is guaranteed to reach exactly one default watchlist
    -- via application-layer provisioning (a new use case,
    -- EnsureDefaultWatchlistUseCase, called on first watchlist-dashboard
    -- load if the user has zero watchlists — NOT wired into registration
    -- itself, since Auth (Phase 2) is frozen and must not be modified).

ALTER TABLE watchlist_items ADD COLUMN position INTEGER NOT NULL DEFAULT 0;
    -- User-chosen display order within a watchlist, distinct from added_at
    -- (insertion order). Reordering rewrites the position values of the
    -- affected items (application-layer concern, not a schema concern) —
    -- no gaps-allowed/fractional-position scheme is used, since watchlists
    -- are small (tens of symbols, not thousands), making a full-rewrite
    -- reorder O(n) and cheap.
ALTER TABLE watchlist_items ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT false;
    -- No uniqueness constraint — multiple items within one watchlist may be
    -- pinned simultaneously (favoriting is not mutually exclusive the way
    -- is_default is at the watchlist level).

CREATE INDEX idx_watchlist_items_watchlist_position ON watchlist_items(watchlist_id, position);
```

**API surface** (extends, does not replace, Document 4's catalog):

```
POST   /api/v1/watchlists                          # NEW — create
PATCH  /api/v1/watchlists/{id}                      # NEW — rename
DELETE /api/v1/watchlists/{id}                      # NEW — delete
GET    /api/v1/watchlists                           # unchanged (list, now with pagination/filter/sort per founder's explicit ask)
GET    /api/v1/watchlists/{id}                      # NEW — get one, with enriched items (Phase 4 market-data integration)
POST   /api/v1/watchlists/{id}/items                # unchanged path, request body extended (accepts symbol, resolved to instrument_id server-side, matching the market_data_router.py convention of {symbol}-keyed routes for anything user-facing)
PATCH  /api/v1/watchlists/{id}/items/{itemId}       # NEW — pin/unpin, reorder
DELETE /api/v1/watchlists/{id}/items/{itemId}       # unchanged
```

## Consequences

- **Easier:** the watchlist model now correctly represents every capability the founder explicitly requested (multiple watchlists, default watchlist, custom ordering, pinning, rename, delete), with database-level enforcement (not just application-layer trust) for the two rules that matter most for data integrity: no duplicate symbol per watchlist (already existed) and at most one default watchlist per user (new).
- **Given up (for now):** no watchlist-sharing/collaboration (a watchlist visible to more than one user) — not requested, out of scope; no per-item custom notes/tags — not requested.
- **Reversible:** yes — all four new columns are nullable-compatible additive changes (three have safe defaults, `is_default`/`updated_at`/`position`/`is_pinned` all backfill cleanly for existing rows); downgrading is a `DROP COLUMN`/index revert with no data loss for pre-existing rows.
- **No existing frozen-architecture table or column is modified or removed.** `Document 4`'s three original endpoints remain valid; this ADR only adds new ones alongside them.

## Alternatives Considered

- **Store `position` as a float/fractional-rank (e.g. Figma-style fractional indexing) to avoid rewriting every item's position on reorder.** Rejected for this phase: watchlists are small (the founder's requirement is "tens of symbols to monitor," not thousands), so an O(n) full-rewrite reorder is simple, correct, and fast enough; fractional indexing adds real complexity (precision exhaustion after many reorders, needing periodic renormalization) that isn't justified at this scale. Documented here as the upgrade path if watchlist sizes ever grow enough to matter.
- **Make `is_default` a foreign key on `users` (`users.default_watchlist_id`) instead of a boolean flag on `watchlists`.** Rejected: Auth (`users` table, Phase 2) is frozen and must not be modified except for critical defects; a flag on the already-mutable `watchlists` table achieves the same guarantee without touching frozen schema.
- **Skip pinning/custom-ordering for this phase, ship only multi-watchlist CRUD.** Rejected: explicitly requested by the founder for Phase 5; deferring would contradict the standing "do not scaffold, actually implement" instruction.
