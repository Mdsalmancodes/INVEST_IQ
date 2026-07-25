# Phase 6 — Known Issues

Issues and disclosed scope decisions identified during Phase 6 (Alerts & Notifications) that remain unresolved or are deliberate, documented boundaries — not defects. Follows the same category scheme used in `docs/phase-1/known-issues.md` (C = environment limitations, D = external tooling limitations) plus a new category for disclosed scope decisions inherited from pre-existing code.

## Category B — Disclosed Scope Decisions (inherited, not introduced this phase)

### B1. No alert-evaluation engine exists — alerts do not yet self-trigger
**What:** `Alert.can_trigger_now()` and `Alert.trigger()` are fully implemented and unit-tested, and `AlertRepository.list_active_for_instrument()` is fully implemented and unit-tested, but no scheduled task or event handler calls them. A user can create, update, list, and delete alerts via the API/UI; nothing currently evaluates a live or historical price against an alert's condition and threshold to decide whether to trigger it.
**Why this is not a Phase 6 defect:** This boundary was set before Phase 6 began. `alert_models.py`'s module docstring (written in a prior session, read but not modified this phase) explicitly documents that the architecture's specified Redis Streams/WebSocket real-time delivery layer is gated to a later phase than "this alerts work," and that triggered alerts will persist to the `notifications` table (built this phase) rather than a Stream, as an interim design. The founder's Phase 6 instruction scoped this session to "Alerts & Notifications" as CRUD/read/preferences surfaces, consistent with how every other bounded context in this codebase (Portfolio, Watchlist) was built incrementally — data model and CRUD first, background processing/automation as an explicit follow-up phase.
**Upgrade path:** `alert_models.py`'s docstring already names the exact integration point: a new Celery task (mirroring the existing `infrastructure/market_data/tasks.py` pattern) would call `AlertRepository.list_active_for_instrument(instrument_id)` whenever a new price arrives, check `alert.can_trigger_now()` for each, call `alert.trigger()` and `alert_repository.save(alert)` on a match, and create a `Notification` via `NotificationRepository.save()`. No other code in either bounded context would need to change.
**Architecture impact:** None. This is the frozen architecture's own documented phasing, not a deviation.

### B2. Notification preferences are not yet consulted by any delivery path
**What:** `NotificationPreferences` (`price_alerts_email`, `price_alerts_push`, `digest_frequency`, quiet hours) is fully persistable and editable via `GET`/`PATCH /api/v1/notifications/preferences` and the `NotificationPreferencesForm` UI component, but since no evaluation engine exists yet (B1), nothing currently reads these preferences to decide whether to actually send an email, a push notification, or respect quiet hours.
**Why this is not a Phase 6 defect:** Directly downstream of B1 — there is no delivery decision point yet for preferences to gate. Building the preferences CRUD surface ahead of the engine that will consume it mirrors the same "data model first" pattern noted in B1, and matches this phase's explicit scope (Alerts & Notifications as data/API surfaces).
**Upgrade path:** Once the B1 evaluation engine exists, its notification-creation step would consult `NotificationPreferenceRepository.get_by_user_id()` before creating a `Notification` row (or before handing off to an email/push delivery mechanism), respecting `digest_frequency`/quiet-hours as a filter.
**Architecture impact:** None.

## Category C — Operating System Limitations (carried forward, re-confirmed this session)

### C1. Windows PowerShell conda-hook noise on every command
**What:** Every shell command in this environment prefixes its output with a harmless `EnvironmentNameNotFound: Could not find conda environment: proctifyAI` error and a PowerShell `Invoke-Expression` binding error.
**Impact:** Cosmetic only — re-confirmed this session across every `poetry run`/`pnpm` invocation; never affected an actual exit code or the substance of any command's stdout used for pass/fail determination in this phase's verification.
**Resolution path:** Unchanged from Phase 1 — out of scope for this project.

## Category D — External Tooling Limitations (carried forward, re-confirmed this session)

### D1. Next.js `output: "standalone"` build fails on this Windows machine (EPERM on symlink creation)
**What:** Re-reproduced this session identically to Phase 1's original finding — `pnpm build` (via turbo) compiles successfully and generates all static pages, but fails during the standalone-output file-tracing step with `EPERM: operation not permitted, symlink ...`.
**Impact on Phase 6 verification:** Playwright E2E tests for the two new specs (`alerts.spec.ts`, `notifications.spec.ts`) were run against `next dev`, matching every prior phase's documented workaround — this verifies route-guard/rendering logic correctly, but is not the production-build code path.
**Resolution path:** Unchanged from Phase 1 — Docker (Linux) remains the authoritative build-verification path once available.

### D2. Docker / Docker Compose not installed
**What:** Re-confirmed this session — `docker --version` still returns "not recognized."
**Impact on Phase 6:** Blocks execution of the 17 new integration tests written this phase (9 for `SqlAlchemyAlertRepository`, 8 for `SqlAlchemyNotificationRepository`/`SqlAlchemyNotificationPreferenceRepository`), bringing the cumulative written-but-unexecuted integration-test count to 55 across all phases (38 from Phases 3–5 + 17 new). All 17 new integration tests were statically verified (ruff clean, mypy strict clean) and are structurally identical in pattern to the already-partially-executed-in-CI-elsewhere Phase 5 watchlist integration tests, but have not themselves been run against a real Postgres instance in this environment.
**Resolution path:** Unchanged from Phase 1 — founder-level decision to install Docker Desktop, outside this session's scope per standing safety guardrails (a substantial system-level install).

## Accepted Technical Debt (not blockers, tracked for future phases)

- **No shared dashboard navigation shell** linking Portfolios/Watchlists/Alerts/Notifications/Markets — carried forward from every prior phase; `/dashboard/alerts` and `/dashboard/notifications` are reachable only by direct URL or by a link from wherever a future nav shell would place them.
- **`NotificationsList`/`AlertsList` poll on a fixed interval (30s) rather than using a WebSocket/live-push mechanism** — a disclosed, deliberate simplification consistent with B1/B2 above (no real-time layer exists yet), matching Watchlist's identical 30s-poll pattern for live quotes established in Phase 5.
- **No pagination controls in the `AlertsList`/`NotificationsList` UI** — both the backend (`page`/`page_size` query params) and the API client (`ListAlertsParams`/`ListNotificationsParams`) support pagination, but the current UI components always request the first page with the default page size and do not yet expose "next page" controls. Out of this phase's explicit scope (the founder's instruction described alerts/notifications management, not pagination UX); a straightforward follow-up once list sizes in practice warrant it.
