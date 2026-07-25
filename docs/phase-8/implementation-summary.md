# Phase 8 — Implementation Summary

**Scope:** Enterprise Security. Secure every backend service; ensure the AI Service is never directly exposed (all AI access proxied through Core API); JWT authentication + refresh tokens (extending Phase 2's existing implementation); Role-Based Access Control (Admin/Premium User/Basic User, Admin-only model training/retraining/deletion/registry access); API Gateway pattern; rate limiting; request validation; secure headers; CORS; CSRF review; SQL injection/XSS protection; Redis token blacklist; audit logging; security middleware; API versioning. Frontend: Permission Guards, Protected Routes, Session Management, Auto Logout, Refresh Token Handling.

**Governing constraint:** Do not modify already-completed features (Phases 1–7) except via strictly additive extensions (optional/defaulted parameters, new files, new endpoints).

## 0. Investigation Finding That Reshaped This Phase's Scope

Before writing any code, a full investigation of the existing codebase found that **Phase 2 had already built substantially more security infrastructure than expected**: a 4-role `Role` enum embedded in every JWT, a fully-implemented (but zero-call-site) `require_role()` RBAC dependency, a kid-based-rotation `JwtProvider`, a login-specific Redis rate limiter, and a complete audit-logging subsystem already wired into `login_use_case.py`. This changed Phase 8's actual work from "build RBAC/audit/rate-limiting from scratch" to "wire up already-existing-but-unused pieces + fill the genuine remaining gaps." This finding is the reason several tasks below are described as "wiring," not "building."

## 1. Role-Based Access Control

**Decision — role naming:** core-api's existing `Role` enum (`domain/auth/entities.py`) has four values: `USER`, `PRO_USER`, `ADMIN`, `SUPER_ADMIN`. The founder's instruction named three tiers ("Admin/Premium User/Basic User"). Rather than renaming the enum — which would touch JWT claim values, database columns, and every Phase 2 auth test for a cosmetic reason — the existing enum was kept as-is. The mapping to user-facing terminology is: `USER` = "Basic User", `PRO_USER` = "Premium User", `ADMIN` and `SUPER_ADMIN` = "Admin" (both included in every admin-only `allowed_roles` list). This is a naming/mapping decision, not an architecture change.

**The actual gap:** `presentation/dependencies/rbac.py`'s `require_role(allowed_roles: list[Role])` dependency was fully implemented from Phase 2 but had zero call sites anywhere in the codebase. Phase 8 applies it for the first time, gating the AI proxy's four admin-only endpoints (see §2).

## 2. AI Proxy — The API Gateway Pattern

This is the centerpiece of Phase 8, directly implementing the "AI Service must never be directly exposed" requirement as a **code-level, testable property**, not merely a deployment/network-topology convention.

**ai-service side (additive):**
- `InternalServiceAuthMiddleware` (`presentation/internal_auth_middleware.py`) rejects (403, `DIRECT_ACCESS_FORBIDDEN`) any request to `/api/v1/ml/*` lacking a matching `X-Internal-Service-Token` header. `/api/v1/ml/metrics` is exempted for monitoring scrapers.
- `DELETE /api/v1/ml/models/{model_version_id}` added (`DeleteModelUseCase` + `ModelRegistryRepository.delete()`), completing the model registry's CRUD surface — this endpoint was needed for the AI proxy's admin-only delete action but did not exist anywhere before this phase.

**core-api side (new bounded context, `application/ai_proxy/` + `infrastructure/http/`):**
- `AiServiceClient` Protocol (11 methods, 1:1 with every ai-service `ml_router` endpoint).
- `HttpAiServiceClient` — the only code in the monorepo that sends `X-Internal-Service-Token`.
- `MockAiServiceClient` — finally implements the mock-client pattern `config.py`'s comments have referenced since Phase 2 but was never built; used when `ai_service_mode="mock"`.
- `ai_proxy_router.py`, prefix `/api/v1/ai` (distinct from ai-service's now-internal-only `/api/v1/ml`):
  - **Authenticated-only** (any role): predict, recommendation, forecast, sentiment, portfolio-recommendation, history.
  - **Admin-only** (`require_role([Role.ADMIN, Role.SUPER_ADMIN])`): model status, train, retrain, delete. The three mutating actions each call the existing `AuditLogger` afterward (see §6).

## 3. Redis Token Blacklist

Phase 2's `token_version` mechanism already provided a *blanket* revocation (bump the version, every token for that user becomes invalid). What was missing was per-token, immediate revocation of a single access token on logout — previously, logging out only deleted the refresh token; the still-valid access token remained usable for the rest of its 15-minute TTL.

- `JwtProvider` gained a `jti` (unique token id) claim, generated per token, with a backward-compatible fallback (empty string) for tokens issued before this change.
- `TokenBlacklist` (`infrastructure/security/token_blacklist.py`) is a thin Redis SET/EXISTS wrapper reusing the existing `get_redis_clients().session` client (no new Redis instance).
- `get_current_user()` checks the blacklist after signature verification; `LogoutUseCase` blacklists the presented access token's `jti` with a TTL matching its remaining natural lifetime.
- **Behavior change:** `POST /api/v1/auth/logout` now requires authentication (previously anonymous) — necessary so the endpoint knows which token to blacklist. Any legitimate client calling logout already holds a valid access token, so this is not a new burden.
- `LogoutEverywhereUseCase` was deliberately left untouched — its existing `token_version` bump already achieves a broader invalidation, making per-`jti` blacklisting redundant there.

## 4. Rate Limiting Middleware

A new general-purpose `RateLimitMiddleware` (Starlette `BaseHTTPMiddleware`) coexists with the pre-existing login-specific `LoginRateLimiter`. Fixed-window Redis INCR+EXPIRE, keyed by authenticated user id (parsed from the JWT directly in middleware, since `Depends()` resolution runs after middleware) or client IP. A stricter, lower window applies specifically to the AI proxy's `train`/`retrain` endpoints. `/health`/`/ready` are exempt.

**Design note — fail-open:** the middleware wraps its Redis calls in `try/except RedisError` and allows the request through if Redis is unreachable. This is disclosed in detail in `known-issues.md` as a defect found and fixed during this phase, and is the correct production posture regardless of environment (a Redis outage must never take down the whole API).

## 5. Security Middleware — Headers, CORS, CSRF, SQLi/XSS

- **Secure headers:** `SecurityHeadersMiddleware` (core-api) applies HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and Permissions-Policy to every response, using the exact values from `docs/architecture/06-security-testing-strategy.md` §15.5. It deliberately omits CSP — §15.5 itself specifies CSP belongs at the BFF/Next.js layer, since CSP governs what the *browser* may load for pages a service serves, and core-api never serves HTML. `apps/web/middleware.ts` was extended (not rewritten) to carry the full CSP directive set plus the same non-CSP headers, applied to every route.
- **CORS:** core-api's previously wide-open `allow_methods=["*"]`/`allow_headers=["*"]` was tightened to the explicit set the API actually uses.
- **CSRF:** audited, not implemented, with disclosed reasoning (see `known-issues.md`) — the current architecture is inherently CSRF-immune because no auth credential is ever carried in an automatically-attached browser cookie.
- **SQL injection:** audited — every repository across core-api uses SQLAlchemy's parameterized query builder; zero raw string interpolation found anywhere. No code changes.
- **XSS:** audited — zero uses of `dangerouslySetInnerHTML`/`innerHTML` anywhere in `apps/web`; React's JSX auto-escaping applies universally. No code changes.

## 6. Audit Logging

Phase 2 already wired `AuditLogger` into `login_use_case.py`; this phase's AI proxy work (§2) added `ai.model.{train,retrain,delete}` entries. Cross-referencing the architecture document's full required event list found two remaining gaps, both closed additively:
- **Password change** — `ResetPasswordUseCase` gained an optional `audit_logger` parameter, recording `auth.password_change`.
- **Large transaction** — `AddTransactionUseCase` (a completed Phase 3 use case) gained optional `audit_logger`/`large_transaction_threshold_usd` parameters, recording `portfolio.large_transaction` when a transaction's value meets/exceeds a configurable threshold (default $10,000).

Events with no corresponding feature anywhere in the codebase (email change, role change, 2FA, API keys, account deletion) were **not** instrumented — there is nothing to audit-log for a capability that does not exist. Logout/logout-everywhere were considered and deliberately not added — not named in the architecture document's list, and adding them would be scope creep beyond the explicit requirement.

## 7. API Versioning

Investigation confirmed every router in both services already used the `/api/v1/` URL-path prefix consistently, with zero exceptions (`/health`/`/ready` correctly excluded, matching standard practice for infrastructure probes). This was therefore a verification/formalization task, not a code change.

**Policy (formalized this phase):**
- **Scheme:** URL-path versioning, `/api/v{N}/`. Current version: `v1`.
- **Introducing v2:** a hypothetical breaking change would be introduced as a new `/api/v2/` prefix served alongside continued `/api/v1/` support, never as an in-place breaking change to `/api/v1/`.
- **Deprecation:** once `/api/v2/` exists, `/api/v1/` would enter a deprecation window (communicated via response headers and/or documentation) before eventual removal, giving existing clients (the `apps/web` frontend, any future third-party integrations) time to migrate.
- **Distinct from software release version:** both services' OpenAPI `version` field (`"0.1.0"`) is the software release semver, unrelated to and independent from this URL-path API contract version.

## 8. Frontend — Permission Guards, Protected Routes, Session Management

**Role awareness (`apps/web`):** `store/types.ts`'s `Role` type already modeled all four backend roles. `store/auth-store.ts`'s `AuthUser` interface existed but was never populated. This phase added `lib/jwt.ts` — a small, dependency-free base64url JWT payload decoder (no signature verification; that remains core-api's job) — and wired it into `setAccessToken()`, so the store now exposes `user: {userId, role}`, `expiresAt`, and a `hasRole(roles)` helper.

**Permission Guards:** `<RequireRole allowedRoles={[...]}>` (`features/auth/components/RequireRole.tsx`) conditionally renders children based on the current role. Exports an `ADMIN_ROLES` convenience constant. Explicitly documented as a UX convenience, not a security boundary — the real enforcement is core-api's `require_role` dependency.

**Protected Routes:** every existing `/dashboard/*` page already had an identical inline client-side auth-gate `useEffect`. Per the "do not modify completed features" rule, these were **not** refactored. Instead, `useProtectedRoute()` (`features/auth/hooks/useProtectedRoute.ts`) formalizes the pattern as reusable, additive infrastructure for pages built from Phase 8 onward, additionally supporting an optional role requirement (redirecting to `/dashboard`, not `/login`, when the user is authenticated but lacks the required role).

**Session Management, Auto Logout, Refresh Handling:** `useSessionManager()` (`features/auth/hooks/useSessionManager.ts`), mounted once in the root `app/providers.tsx` so it runs app-wide with no per-page wiring, provides two independent mechanisms:
1. **Proactive refresh** — schedules `authApi.refreshAccessToken()` ~2 minutes before the current access token's expiry (read from the store's `expiresAt`). On success, the rotated token replaces the old one. On failure, the session is cleared and the user is redirected to `/login` immediately, rather than waiting for a reactive 401.
2. **Idle-timeout auto-logout** — tracks mouse/keyboard/scroll/touch activity; after 30 minutes with none, the session is cleared and the user redirected, independent of whether the access token is still technically valid.

**Bug found and fixed:** `authApi.logoutCurrentSession()` sent no `Authorization` header, but Task 4's backend change made `POST /api/v1/auth/logout` require authentication. Fixed by making the access token a required parameter, sent via the existing request helper's `accessToken` option.

## 9. Frontend — AI Dashboard Rewired to the Proxy

`lib/ai-api.ts` previously called ai-service directly (`NEXT_PUBLIC_AI_SERVICE_BASE_URL`, unauthenticated) — the disclosed Phase 7 gap A1/A2. It now targets core-api's `/api/v1/ai/*` proxy, using the same `authorizedRequest<T>()` convention already established by `lib/portfolio-api.ts` (reads the access token from the store internally; throws `NOT_AUTHENTICATED` if absent). The public `aiApi` method names and payload/response shapes are unchanged, so no caller-side signature breakage occurred. A `deleteModel()` method was added, exposing the AI proxy's new admin-only DELETE endpoint for the first time on the frontend.

A new `ModelAdminPanel` (inside `features/ai/components/ModelStatus.tsx`, gated by `<RequireRole allowedRoles={ADMIN_ROLES}>`) is genuinely new UI — no admin action controls (train/retrain/delete) existed in the frontend before this phase. `NEXT_PUBLIC_AI_SERVICE_BASE_URL` was removed from `.env.example` since the frontend no longer talks to ai-service directly at all.

## 10. Architecture Decision Records

**No ADR was required for Phase 8.** Every change either (a) wires up already-existing-but-unused infrastructure from Phase 2 (`require_role`, the audit-logging subsystem, `JwtProvider`), or (b) is a straightforward additive extension explicitly named in the phase's own instruction (Redis blacklist, rate limiting, security headers, audit-logging gap closures). Nothing reversed or deviated from a previously frozen architectural decision.
