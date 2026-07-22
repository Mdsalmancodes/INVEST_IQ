# Architecture Decision Records (ADR)

This directory contains ADRs for INVEST IQ. The architecture blueprint in `docs/architecture/01` through `08` (plus `REVIEW-LOG.md`) is **frozen** as of founder approval on 2026-07-21.

## When an ADR is required

Per founder instruction, the frozen architecture must not be silently modified. Create an ADR **before** making the change, in any of these situations:

- A documented design turns out to be genuinely unimplementable (a real blocker — not a preference).
- A documented design is being deliberately descoped for project constraints (e.g., final-year project timeline/team-size realism) rather than dropped due to a blocker.
- A new technology/library choice replaces one named in the blueprint.
- A schema, API contract, or module boundary defined in the blueprint needs to change.

Small clarifications that don't change behavior (fixing a typo, adding a code comment) do not need an ADR. When in doubt, write one — they're cheap.

## Process

1. Copy `template.md` to `NNNN-short-title.md` (4-digit sequential number, e.g. `0001-single-redis-instance-for-final-year-scope.md`).
2. Fill in Context, Decision, Consequences, Alternatives Considered.
3. Reference the specific blueprint document/section being superseded.
4. Set status to `Proposed` until reviewed, then `Accepted` (or `Rejected`/`Superseded` if applicable).
5. Add a one-line pointer comment in the affected blueprint document (`> See ADR-000N for a scope change to this section.`) so the blueprint and the ADR log stay cross-referenced — the blueprint document itself is never silently rewritten.

## Index

| ADR | Title | Status | Supersedes |
|---|---|---|---|
| [0001](./0001-python-3.11-local-dev-compatibility.md) | Python 3.11 for Local Development, Python 3.12 Preserved as Production/Docker Target | Accepted | Doc 7 §17.3 Dockerfile Python version examples (local dev constraint only — Docker images unaffected) |
| [0002](./0002-login-history-table.md) | Add `login_history` Table for Login History & Device Tracking | Accepted | Doc 3 §8.1 (additive only — no existing table modified) |
| [0003](./0003-split-transfer-transaction-types.md) | Extend `transactions.type` to Include `split` and `transfer` | Accepted | Doc 3 §8.1 (additive: CHECK constraint values + 2 new nullable columns, no existing column modified) |
| [0004](./0004-watchlist-multi-list-ordering-pinning.md) | Extend `watchlists`/`watchlist_items` for Multi-Watchlist, Ordering, Pinning, and Default-Watchlist Support | Accepted | Doc 3 §8.1 (additive: 4 new columns + 2 new indexes, no existing column modified), Doc 4 Watchlist endpoint catalog (additive: 4 new endpoints alongside the 3 existing) |
