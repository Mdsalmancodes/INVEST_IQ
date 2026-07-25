# Phase 8 — Verification Report

## 1. Backend Verification (core-api)

Commands run from `apps/core-api`:

```
poetry run ruff check .
poetry run mypy src
poetry run pytest -q
```

**Result:** ruff — all checks passed. mypy — success, no issues found in 174 source files. pytest — **459 passed, 55 deselected** (Docker-unavailable integration tests, carried forward from every prior phase since Phase 3), 1 pre-existing warning (HMAC key length notice, unrelated to this phase).

**Baseline comparison:** 401 tests passing at the end of Phase 7 → 459 at the end of Phase 8 (**+58 net new tests**), zero regressions.

New test files/additions this phase, by task:
- Task 2+3 (RBAC + AI proxy): 33 tests — `test_ai_proxy_router.py` (17), `test_ai_service_client.py` (7), `test_mock_ai_service_client.py` (9).
- Task 4 (Redis token blacklist): 24 tests — `test_jwt_provider.py` (+2), `test_token_blacklist.py` (5, new), `test_logout_use_case.py` (+3), `test_get_current_user_blacklist.py` (2, new), `test_logout_router.py` (2, new).
- Task 5 (rate limiting): 4 tests — `test_rate_limit_middleware.py` (new).
- Task 6 (security middleware): 2 tests — `test_security_headers_middleware.py` (new).
- Task 7 (audit logging): 5 tests — `test_reset_password_use_case.py` (+2), `test_use_cases.py`'s `TestAddTransactionUseCase` (+3).

## 2. Backend Verification (ai-service)

Commands run from `apps/ai-service`:

```
poetry run ruff check .
poetry run mypy src
poetry run pytest -q
```

**Result:** ruff — all checks passed. mypy — success, no issues found in 53 source files. pytest — **202 passed**.

**Baseline comparison:** 193 tests passing at the end of Phase 7 → 202 at the end of Phase 8 (**+9 net new tests**), zero regressions.

New tests this phase: `test_delete_model_use_case.py` (2), `test_internal_auth_middleware.py` (5), `TestDeleteModelEndpoint` class in `test_ml_router_remaining_endpoints.py` (2).

## 3. Frontend Verification (apps/web)

Commands run from `apps/web` (via `pnpm --filter @investiq/web ...`):

```
pnpm typecheck
pnpm lint
pnpm test:unit
npx playwright test
```

**Result:**
- `typecheck` — clean, zero errors.
- `lint` — clean, zero errors/warnings.
- `test:unit` — **156 passed** (37 test files).
- `playwright test` (full suite, 9 spec files) — **18 passed**, 4 failed (see §5 below — pre-existing, not a Phase 8 regression).

**Baseline comparison:**
- Unit tests: 118 (Phase 7 baseline) → 156 (**+38 net new tests**), zero regressions.
- E2E specs: 17 passing (Phase 7 baseline) → 18 passing (+1 new spec), plus the same 4 pre-existing failures carried forward unchanged.

New unit test files/additions this phase, by task:
- Task 11 (permission guards/protected routes): 19 tests — `lib/jwt.test.ts` (7, new), `store/auth-store.test.ts` (7, new), `features/auth/components/RequireRole.test.tsx` (5, new).
- Task 12 (session management/auto logout/refresh): 7 tests — `features/auth/hooks/useSessionManager.test.ts` (5, new), `lib/auth-api.test.ts` (2, new).
- Task 13 (AI dashboard proxy rewiring): 8 tests — `features/ai/components/ModelStatus.test.tsx` (+4), `lib/ai-api.test.ts` (4, new — different assertions than Task 12's initial version, replaced/superseded during Task 13).
- Task 14 (coverage gap review): 4 tests — `features/auth/hooks/useProtectedRoute.test.ts` (4, new).

New E2E spec: `e2e/phase8-admin-panel.spec.ts` (1 test).

## 4. Combined Monorepo Totals

| Suite | Phase 7 baseline | Phase 8 final | Net new |
|---|---|---|---|
| core-api unit/integration | 401 passing (+55 deselected) | 459 passing (+55 deselected) | +58 |
| ai-service unit | 193 passing | 202 passing | +9 |
| apps/web unit | 118 passing | 156 passing | +38 |
| apps/web E2E | 17 passing | 18 passing (+4 pre-existing failures, unchanged) | +1 |
| **Grand total (passing)** | **729** | **835** | **+106** |

## 5. Zero Regressions to Phases 1–7 — How Verified

Every full-suite command above was re-run **fresh** during this session (not assumed from "no files touched"). Additionally:
- The rate-limiter fail-open bug (§ known-issues.md, Category A1) was caught precisely because the *full* pre-existing suite was re-run after each middleware change, not just newly-added tests — the entire 434-test baseline briefly broke before the fix, and was confirmed fully passing again immediately after.
- `git diff --stat HEAD` was used before concluding the 4 pre-existing E2E failures (below) were unrelated to this phase — it showed zero changes to any file in the login/register render or validation path.

## 6. Pre-Existing E2E Failures — Not a Phase 8 Regression

4 of the 22 total E2E tests fail consistently, both before and after every Phase 8 change:
- `auth.spec.ts` — "login page renders and validates client-side", "register page shows password strength meter as the user types", "register page validates mismatched passwords client-side"
- `markets.spec.ts` — "typing in the search box shows a result state (error, since no backend is running)"

All four are client-side Zod-validation-message or error-state rendering assertions that time out fast (~9.3s, well under any configured timeout) because the expected text never appears — not a late-appearing/flaky timing issue. Investigated thoroughly (see `known-issues.md` §D3 for the full investigation) and confirmed to be a pre-existing, environment-specific condition on this constrained Windows development machine, unrelated to any file touched this phase. The Phase-8-relevant specs (`ai.spec.ts`'s route guard, `watchlist.spec.ts`, `portfolio.spec.ts`, `home.spec.ts`, the new `phase8-admin-panel.spec.ts`) all pass cleanly.

## 7. Manual/Exploratory Verification

- `app.openapi()` was invoked programmatically against core-api's app object to confirm all 10 new `/api/v1/ai/*` paths registered correctly (Task 2+3).
- Both `.env.example` files (ai-service, core-api) were confirmed to carry matching `INTERNAL_SERVICE_TOKEN` values so the AI proxy round-trip works end-to-end in local dev, once both services are actually running.
