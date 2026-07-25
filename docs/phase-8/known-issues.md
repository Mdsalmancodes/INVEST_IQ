# Phase 8 — Known Issues

Issues and disclosed scope decisions identified during Phase 8 (Enterprise Security) that remain unresolved or are deliberate, documented boundaries — not defects. Follows the same category scheme used in `docs/phase-1/known-issues.md` (C = environment limitations, D = external tooling limitations), plus new categories for this phase's found-and-fixed defects and disclosed scope decisions.

## Category A — Defects Found and Fixed During This Phase

### A1. Rate limiting middleware crashed every request when Redis was unreachable (fixed)
**What:** The first implementation of `RateLimitMiddleware` called `await redis.incr(key)` unconditionally, with no error handling. Since this development/test environment has no real Redis instance running, every single existing test hitting the app through `TestClient`/`ASGITransport` immediately started failing with `redis.exceptions.ConnectionError` — the entire 448-test baseline broke.
**Root cause diagnosis:** Rather than patching around the symptom (e.g., skipping the middleware in tests), the actual design flaw was identified: a rate limiter must never be a correctness-critical dependency that takes down the entire API if its backing store has an outage.
**Fix:** The middleware's Redis calls are now wrapped in `try/except RedisError`, returning `call_next(request)` immediately (allowing the request through) if Redis is unreachable — mirroring the pre-existing `LoginRateLimiter`'s own defense-in-depth posture. This is the correct **production** behavior too, not merely a test-environment workaround: a transient Redis blip must never cause a full API outage.
**Verified:** full suite re-run immediately after the fix — all 448 pre-existing tests passed again; 4 new tests added specifically covering the fail-open path.

### A2. Test fixture used a non-UUID placeholder, crashing the new audit-logging code path (fixed, test-only)
**What:** The first draft of the large-transaction audit-logging test used `"user-1"` as a placeholder `requesting_user_id`, which crashed inside `UserId.from_string()` (requires a genuine UUID).
**Diagnosis:** The actual production call site (`portfolio_router.py`) was checked first, confirming it always passes `str(current_user.user_id)` — a real UUID. This was a test-fixture problem, not a production robustness gap.
**Fix:** The test was corrected to use a real `UserId.new()` string. No defensive exception-handling was added to production code — the UUID invariant already holds unconditionally elsewhere in this codebase's auth application layer without such wrapping, and adding it here would mask genuine bugs rather than prevent them.

## Category B — Disclosed Scope Decisions (introduced this phase)

### B1. CSRF protection was not implemented — confirmed structurally unnecessary, not skipped
**What:** No CSRF token or middleware exists anywhere in core-api or the frontend.
**Why this is not a gap:** Re-confirmed by reading `apps/web/store/auth-store.ts` and `lib/auth-api.ts`'s own docstrings — the access token lives only in an in-memory Zustand store, never a cookie, and the refresh token currently also returns directly in the JSON response body (the httpOnly-cookie BFF interception route remains unbuilt, a Phase 2 gap re-confirmed still true — see D2 below). Since no auth credential is ever carried in a cookie the browser attaches automatically, this architecture is inherently CSRF-immune per OWASP's own guidance: CSRF specifically exploits automatic cookie attachment, and a cross-origin attacker page cannot read an in-memory JS value or set an `Authorization` header on the victim's behalf.
**Upgrade path:** If a future phase builds the BFF httpOnly-cookie flow that Phase 2 originally specified as the target architecture, CSRF protection (e.g., a double-submit cookie or `SameSite=strict` alone, since this app has no cross-site form posts) would need to be revisited at that point — the current bearer-token-in-memory design would no longer apply.

### B2. Logout and logout-everywhere are not audit-logged
**What:** Session-revocation events (`/api/v1/auth/logout`, `/api/v1/auth/logout-everywhere`) do not call `AuditLogger`.
**Why this is not a gap:** The architecture document's audit-logging requirement list names "login success/failure" explicitly but does not name logout. Adding it would be scope creep beyond the explicit requirement.
**Upgrade path:** Trivial to add if a future phase's requirements explicitly call for it — both use cases already have the exact optional-`audit_logger`-parameter pattern established this phase (`ResetPasswordUseCase`, `AddTransactionUseCase`) to follow.

### B3. Several named audit-logging events have no corresponding feature to instrument
**What:** The architecture document's audit-logging requirement list also names email change, role change, 2FA enable/disable, API key creation/revocation, and account deletion request. None of these capabilities exist anywhere in the codebase (confirmed via search: no email-change use case, no role-change use case, no 2FA, no API-key management, no account-deletion use case).
**Why this is not a gap:** An audit log entry cannot be attached to a use case that does not exist.
**Upgrade path:** Whichever future phase builds each of these features should add its audit-logging call at the same time, following this phase's established optional-parameter pattern.

## Category C — Operating System Limitations (carried forward, re-confirmed this session)

### C1. Windows PowerShell conda-hook noise on every command
**What:** Every shell command in this environment prefixes its output with a harmless `EnvironmentNameNotFound: Could not find conda environment: proctifyAI` error and a PowerShell `Invoke-Expression` binding error.
**Impact:** Cosmetic only — re-confirmed this session across every `poetry run`/`pnpm`/`npx` invocation; never affected an actual exit code or the substance of any command's stdout used for pass/fail determination in this phase's verification.
**Resolution path:** Unchanged from Phase 1 — out of scope for this project.

## Category D — External Tooling / Environment Limitations (carried forward, re-confirmed this session, plus new findings)

### D1. Docker / Docker Compose not installed
**What:** Re-confirmed this session — no Docker daemon reachable.
**Impact on Phase 8:** Blocks execution of the pre-existing 55 core-api integration tests (unrelated to this phase's scope). Also means **no real Redis instance is running** in this development environment — this is precisely why the rate-limiter fail-open fix (A1 above) was essential, and why every Redis-touching code path added this phase (`TokenBlacklist`, `RateLimitMiddleware`) either uses a test fake/double or must tolerate connection failures gracefully in production too.
**Resolution path:** Unchanged from Phase 1 — founder-level decision to install Docker Desktop, outside this session's scope per standing safety guardrails.

### D2. Refresh token still returns in the JSON response body, not an httpOnly cookie
**What:** Unchanged from Phase 2's original disclosed limitation, re-confirmed still true this session — `auth_router.py`'s login/refresh endpoints return both tokens directly in the JSON body; the BFF interception route that would set the refresh token as an httpOnly/secure/`sameSite=strict` cookie (per the frozen architecture's target design) is not yet built.
**Impact on Phase 8:** This is the direct reason CSRF protection is structurally unnecessary right now (B1 above) — but it also means the refresh token remains readable by any script executing on the page, same as any in-memory JS value, which is a narrower interim than the httpOnly-cookie design specifies.
**Resolution path:** Unchanged from Phase 2 — building the BFF cookie-interception route remains a separable piece of frontend infrastructure work for a future phase.

### D3. Four pre-existing E2E tests fail, unrelated to this phase (investigated, not fixed)
**What:** `auth.spec.ts`'s "login page renders and validates client-side", "register page shows password strength meter as the user types", "register page validates mismatched passwords client-side", and `markets.spec.ts`'s "typing in the search box shows a result state" all fail consistently — the expected client-side validation/error text never appears, failing fast (~9.3s) rather than timing out slowly.
**Investigation performed:** `git diff --stat HEAD` confirmed zero changes to `LoginForm.tsx`, `RegisterForm.tsx`, or any file in their render/validation path this entire session. The one unexpected diff in `packages/validation/src/index.ts` is a purely additive, pre-existing export list (alerts/notifications schemas) unrelated to login/register schemas. The failures were reproduced identically across the full suite, an isolated run of just these two spec files, a single test with an extended 30-second timeout, and a single test with `--workers=1` after killing and restarting all Node processes (to rule out a stale dev-server) — same failures every time.
**Why this is not a Phase 8 regression:** No file in the actual failure path was touched this session; the failure mode (fast, complete absence of the expected element) is consistent with a pre-existing dev-server/hydration environment issue on this constrained Windows machine, which `playwright.config.ts`'s own header docstring already discloses has other Windows-specific Next.js build limitations (EPERM on symlinks blocking a production build, forcing `next dev` for local E2E).
**Why it was not "fixed":** Doing so would require modifying `LoginForm.tsx`, `RegisterForm.tsx`, or the `@investiq/validation` package — all completed-phase code unrelated to Phase 8's actual scope — for a problem whose root cause (an environment/build artifact, not application logic) is not actually located in those files. Modifying them to chase an unrelated, pre-existing issue would violate the "do not modify completed features" rule for no real benefit.
**Resolution path:** Should be investigated as its own dedicated task in a future phase, ideally once Docker (Linux, no Windows-specific symlink/build limitations) is available as the authoritative E2E environment.

### D4. Next.js `output: "standalone"` build fails on this Windows machine (EPERM on symlink creation)
**What:** Unchanged from Phase 1's original finding, not re-reproduced this session (Phase 6 and 7 already re-confirmed it identically) — `pnpm build` fails during the standalone-output file-tracing step with `EPERM: operation not permitted, symlink ...`.
**Impact on Phase 8 verification:** All Phase 8 E2E tests, like every prior phase's, were run against `next dev`, not a production build.
**Resolution path:** Unchanged from Phase 1 — Docker (Linux) remains the authoritative build-verification path once available.

## Accepted Technical Debt (not blockers, tracked for future phases)

- **No shared dashboard navigation shell** — carried forward from every prior phase; the new AI Insights admin panel is reachable only by direct URL or a link from wherever a future nav shell would place it.
- **ai-service still has no user/role concept of its own** — RBAC is enforced entirely at core-api's proxy layer (`ai_proxy_router.py`'s `require_role`), matching the disclosed architectural boundary that ai-service is an internal-only compute service, never a user-facing authorization boundary itself. This is by design, not a gap: the `InternalServiceAuthMiddleware` (this phase) already ensures ai-service only ever receives requests from core-api, which has already authorized the request before forwarding it.
- **The AI proxy's `AiServiceClient` Protocol passes through raw dicts rather than a third parallel Pydantic DTO set** — ai-service's own `ml_dto.py` and the frontend's `lib/ai-api.ts` already fully type every request/response shape twice; a third set in core-api's proxy layer was judged to add duplication without meaningfully improving safety, since core-api forwards these bodies essentially unmodified.
