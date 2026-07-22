# INVEST IQ — Architecture Blueprint
## Document 6 of N: Security Architecture, Testing Strategy

> Status: DRAFT — pending founder approval

---

## 15. Security Architecture

### 15.1 Threat Model Summary (what we are actually defending against)

| Threat | Relevant because | Primary mitigation |
|---|---|---|
| Account takeover | Users' portfolios/financial data | Refresh token rotation, httpOnly cookies, bcrypt, rate-limited login, optional 2FA (Phase 6+) |
| XSS → token theft | Rich UI, user-generated content nowhere currently but news rendering is 3rd-party HTML-adjacent | Access token in memory not localStorage, CSP headers, React's default escaping, sanitize any HTML from news sources before render |
| CSRF | Cookie-based refresh token | SameSite=strict cookies + custom header requirement on state-changing requests (double-submit not needed given SameSite=strict, but CSRF token as defense-in-depth on sensitive actions) |
| SQL/NoSQL injection | Postgres + Mongo | ORM parameterized queries exclusively (SQLAlchemy, PyMongo with proper query builders) — raw string interpolation into queries is a banned pattern, enforced via code review + linting rule where feasible |
| Insecure Direct Object Reference (IDOR) | Portfolio/holding IDs are UUIDs but that alone isn't authorization | Every resource query scoped by `user_id` at the repository layer (Document 3 §7.5), never trust a resource ID alone |
| Rate abuse / scraping / credential stuffing | Public-facing auth + data endpoints | Redis-based rate limiting (Document 4 §9.6), account lockout after N failed logins with exponential backoff |
| Vendor API key leakage | Market data vendor keys are platform secrets, not user secrets | Keys never sent to client, held only in backend service env/secrets manager, requests to vendors proxied server-side only |
| Man-in-the-middle | All traffic | HTTPS/TLS everywhere (enforced via HSTS header), WSS for WebSocket, no plaintext fallback |
| Malicious dependency (supply chain) | Large dependency tree (npm + pip) | Pinned exact versions, automated dependency vulnerability scanning (Dependabot/Snyk) in CI, lockfiles committed |
| Data exposure via logs/errors | Debugging necessity vs. leak risk | Redaction middleware (Document 5 §14.1), generic error messages in production |
| Denial of Service | Public endpoints, WS connections | Rate limiting, connection limits per IP AND per-user on WS (Document 3 §7.6 revision), Cloudflare/CDN-level DDoS protection at the edge (recommended, not built by us) |
| **Algorithmic complexity / DoS via expensive queries** *(gap identified in review — missing entirely)* | Screener/Optimizer accept complex, user-controlled filter/constraint combinations with no cost bound | Screener restricted to a whitelisted pre-materialized factor table with an 8-condition cap; Optimizer bounded to ≤100 holdings with a solver timeout, dispatched async (Document 4 §9.4a) |
| **Prompt injection against the AI Assistant** *(gap identified in review — missing entirely; the assistant's tool-calling design was absent from this table despite being a genuine attack surface)* | LLM-driven tool-calling layer (Document 3 DDD §3.1) could in principle be manipulated via crafted input to attempt unauthorized actions | Every tool invocation re-authorized through the same ownership/RBAC guards as the REST API (Document 4 §9.6a) — authorization is enforced at the tool-execution boundary, never trusted from the LLM's own reasoning; per-user token budget and max tool-call-loop iterations bound worst-case cost/blast radius of a successful injection attempt |
| **Secrets compromise without rotation** *(gap identified in review — storage was covered, rotation was not)* | Long-lived JWT signing keys/vendor keys/DB credentials increase blast radius if ever leaked | Scheduled rotation (§15.4 revision below) |

### 15.2 Authentication Security Detail

- **Password storage**: bcrypt, cost factor 12 (tunable via config as hardware improves — cost factor is not hardcoded as a magic number, it's an env-configurable setting so it can be raised without a code change).
- **Password policy**: minimum 10 characters, checked against a common-password blocklist (e.g., a bundled Have-I-Been-Pwned-style top-10k list) rather than arbitrary complexity rules (complexity rules like "must contain a symbol" are known to produce weaker, more predictable passwords than length-focused policies — NIST 800-63B guidance).
- **Login rate limiting**: 5 failed attempts per account per 15 minutes triggers exponential backoff; 10 failed attempts triggers a temporary account lock + email notification to the account owner.
- **OAuth**: standard authorization code flow with PKCE for Google/GitHub — no implicit flow, no storing OAuth provider tokens longer than needed to establish the internal session.
- **2FA (Phase 6+, designed for now)**: TOTP-based, `User` entity has a `totp_secret_encrypted` field reserved in the schema from day one so adding 2FA later doesn't require an auth-table migration mid-flight for existing users.
- **Session invalidation**: `token_version` bump pattern (Document 3 §7.4) enables instant "log out everywhere," checked on every authenticated request via a cheap Redis-cached lookup (not a Postgres hit per request).

### 15.3 Input Validation

**Validated at every layer boundary, not just one:**

```
Frontend: Zod schema validation on every form before submission (fast UX feedback)
     ↓
BFF: Same Zod schemas (shared via packages/validation) re-validate on the server
     side of the BFF — never trust the client validated correctly, client-side
     validation is UX only, never a security boundary
     ↓
Backend service: Pydantic model validation on every request DTO — this is the
     actual enforced boundary, since internal services could theoretically be
     reached by something other than the BFF in a misconfiguration scenario
     ↓
Domain layer: value objects self-validate on construction (e.g., `Money(-5)`
     raises `InvalidMoneyAmount` — invariants are enforced by the type itself,
     not by remembering to check before use)
```

### 15.4 Secrets Management

- Local dev: `.env` files (git-ignored, `.env.example` committed with placeholder values and comments explaining each var).
- Production: platform secrets manager (AWS Secrets Manager / Doppler / Vault — specific choice deferred to Document 8 DevOps, but the application code reads secrets via environment variables regardless of backing store, so the app layer is agnostic to which secrets manager is chosen operationally).
- **No secret ever committed to git.** `.gitignore` covers `.env*` except `.env.example`; a pre-commit hook (gitleaks or equivalent) scans staged changes for secret-shaped strings as a safety net against accidental commits.
- Database credentials, JWT signing keys, vendor API keys, OAuth client secrets — all sourced from environment/secrets manager, never hardcoded, never logged (Document 5 §14.1 redaction).

**Secrets rotation (missing entirely from the original draft — added per architecture review):**
- **JWT signing keys**: `kid` (key ID)-based rotation — the token header carries a `kid`, the verification side maintains the current key plus a short overlap window of the immediately-previous key, so a rotation doesn't invalidate tokens issued moments before it. Rotation cadence: every 90 days, or immediately on suspected compromise.
- **Vendor API keys / DB credentials**: rotated via the secrets manager's native rotation support (e.g., AWS Secrets Manager automatic rotation with a Lambda rotation function, or equivalent) on a 90-day cadence; application services re-fetch credentials on a TTL rather than caching them for the process lifetime, so a rotation doesn't require a redeploy to take effect.
- Added as an explicit Phase 10 launch checklist item (Document 8 §24) — rotation *capability* existing in the secrets manager is necessary but not sufficient; the *procedure* (who rotates what, on what cadence, how services pick up the change) is what's being tracked.

### 15.5 Security Headers (enforced at BFF/Next.js middleware level)

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'wasm-unsafe-eval';
  connect-src 'self' https://api.investiq.app wss://api.investiq.app https://*.spline.design;
  frame-src 'self' https://my.spline.design;
  worker-src 'self' blob:;
  img-src 'self' data: https://*.investiq-cdn.app;
  style-src 'self' 'unsafe-inline';
  (scoped to allow R3F/Three.js WASM and the Spline embed (§6.6/Doc 2 §6.6) where needed
  via explicit connect-src/frame-src/worker-src directives — the original spec was
  missing these, which a review flagged as underspecified for the Spline embed
  specifically. 'unsafe-inline' on style-src is a scoped, deliberate exception for
  Tailwind's runtime-injected styles, not a blanket allowance; no 'unsafe-inline' for
  scripts under any circumstance.)
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 15.6 Audit Logging (Security-Relevant Events)

Beyond general application logs, security-sensitive actions write to the dedicated `audit_logs` table (Document 3 §8.1) with longer retention and stricter access control (admin-only read, even platform engineers query this through a controlled admin endpoint, not raw DB access in normal operation):

```
Logged: login success/failure, password change, email change, role change,
        2FA enable/disable, API key creation/revocation, large transaction
        (> configurable threshold), account deletion request, admin actions
        on other users' data.
```

### 15.7 Data Privacy Considerations

- PII (email, full name) isolated to the `users` table — never duplicated into Mongo documents or logs.
- Users can request full data export and account deletion (GDPR/CCPA-style right-to-erasure) — architecturally supported via cascading deletes (`ON DELETE CASCADE` already present on user-owned tables) plus a scrubbing job for the audit_logs (which use `ON DELETE SET NULL` deliberately — audit trail integrity for platform security review outlives individual account deletion, but the deleted user's PII is removed from it).
- No PII sent to third-party AI/ML inference beyond what's operationally required (e.g., the AI Assistant's LLM calls include portfolio *data* but never raw email/name unless the user is explicitly asking about their own profile).

---

## 16. Testing Strategy

### 16.1 Testing Pyramid (target distribution)

```
        ┌─────────────┐
        │   E2E (5%)    │        Playwright — critical user journeys only
        ├─────────────┤
        │ Integration    │        Real DB (testcontainers), real HTTP, mocked
        │   (25%)         │        external vendors
        ├─────────────┤
        │                  │
        │   Unit (70%)      │      Domain logic, use cases, pure functions —
        │                  │      no I/O, fast, run on every save in dev
        └─────────────┘

        + a distinct, smaller resilience/chaos tier (§16.2a) — not part of the
          percentage split above since it targets failure-mode coverage, not
          feature coverage, and runs on a different cadence (see §16.6 revision).
```

### 16.2 Backend Testing (Python/FastAPI)

| Level | Tool | What's tested | Example |
|---|---|---|---|
| Unit | pytest | Domain entities/value objects, application use cases with mocked repository interfaces | `Portfolio.apply_transaction()` correctly updates average cost basis on a partial sell |
| Integration | pytest + testcontainers (real Postgres/Mongo/Redis in Docker) | Repository implementations against a real DB, Celery task execution | `SqlAlchemyPortfolioRepository.save()` persists and round-trips correctly including constraint violations |
| Contract (schema-level) | schemathesis (property-based testing against OpenAPI schema) | Every endpoint handles malformed/edge-case input without 500ing | Fuzzing all documented endpoints against the OpenAPI spec |
| Contract (BFF↔service, gap identified in review) | Generated-types CI job (see below) | The BFF's assumptions about a service's response shape actually match what the service returns — schemathesis alone only validates a service against its *own* schema, not that consumers' assumptions stay in sync | A field renamed in `ai-service`'s response DTO breaks `web`'s `tsc --noEmit` at PR time, not at runtime in production |
| E2E | httpx AsyncClient against a fully running app (docker-compose test profile) | Full auth flow, full transaction flow | Register → login → create portfolio → add holding → verify valuation |
| ML-specific | pytest + fixed seeds/fixtures | Feature engineering determinism, backtest harness correctness, SHAP payload shape | Given fixed historical data, feature vector output matches golden fixture exactly |

**Domain layer coverage target: 95%+** (it's pure logic, no excuse for gaps). Infrastructure layer coverage target: 70%+ (some framework glue code isn't worth exhaustive testing). Overall service target: 80%+, enforced in CI (build fails below threshold).

**BFF↔service contract testing detail (gap identified in review — closes it):** on every PR, a CI job regenerates `packages/types` from all backend services' live OpenAPI schemas (`core-api` + `ai-service`, per Document 3 §7.1's revised 2-service topology), then runs `tsc --noEmit` against the `web` app using the freshly generated types. A breaking internal API change (renamed/removed/retyped field) fails the build immediately at PR time — the BFF's "internal services are still required to produce [the envelope] correctly" assumption (Document 3 §7.3) is now mechanically checked, not just stated.

### 16.2a Resilience / Chaos Testing (missing entirely from the original draft — added per architecture review)

Document 3 §7.6 explicitly labels alert evaluation a "Reliability-Critical Path" with real failover mechanisms (Redis Streams consumer groups, `XCLAIM`), yet the original testing pyramid had zero tier verifying those mechanisms actually work under failure. A dedicated resilience suite (`core-api/tests/resilience/`, since the notification module now lives there per Document 3 §7.1) covers:

1. **Consumer crash mid-processing**: kill a Celery worker holding an unacknowledged Alert Stream entry; assert another consumer in the group claims it via `XCLAIM` after the idle timeout and the alert is still delivered exactly once (not zero times, not duplicated).
2. **Slow WS client / backpressure**: simulate a client with a stalled receive buffer; assert the server coalesces to the latest quote tick (Document 3 §7.6) rather than growing an unbounded send queue or blocking other clients.
3. **Redis disconnect/reconnect**: kill and restart the `redis-cache` connection mid-operation; assert the Pub/Sub subscriber auto-resubscribes and quote fan-out resumes without requiring a service restart.
4. **Graceful WS shutdown**: trigger a SIGTERM against a `core-api` instance holding active WS connections; assert connected clients receive the `reconnect_advised` frame (Document 3 §7.6) before the socket closes, and that the client-side reconnection logic (exponential backoff + resubscribe) is exercised end-to-end in a Playwright E2E test, not just unit-tested in isolation.

Gated as a required check in Phase 6 (real-time layer) and re-run in Phase 10 (launch hardening) per Document 8 §24 — not part of the standard per-PR pyramid above, since these tests are slower and target failure-mode coverage rather than everyday feature regressions.

### 16.3 Frontend Testing (Next.js/React)

| Level | Tool | What's tested |
|---|---|---|
| Unit | Vitest + React Testing Library | Hooks (`usePortfolio`), utility functions, Zod schema validation logic |
| Component | Vitest + RTL + MSW (mock service worker for API mocking) | Individual components render correctly across states (loading/error/success), user interactions trigger correct callbacks; per Document 2 §6.1a, every `DataTable` component test includes both `mobileRenderMode` variants |
| Visual regression | Chromatic (Storybook-based) or Playwright screenshot comparison | Design system components (`packages/ui`) don't visually regress across changes, across BOTH light and dark themes (Document 2 §6.3a) |
| E2E (smoke tier, every PR — gap identified in review) | Playwright, 3-5 test subset | The highest-value critical paths only: signup→dashboard, place paper order | Runs on every PR, not just main, so a broken critical path is caught before merge rather than sitting undetected on `develop` |
| E2E (full suite, main branch only) | Playwright | All critical journeys: signup→dashboard, add holding→see updated valuation, place paper order→see it in order history, AI assistant conversation round-trip | Full regression coverage, runs post-merge given its longer runtime |
| Accessibility | axe-core (via `@axe-core/playwright` in E2E, and `eslint-plugin-jsx-a11y` at lint time) | WCAG 2.1 AA compliance on all primary pages, enforcing the component-level design rules in Document 2 §6.5 (not just generic label/contrast checks) |
| Performance | Lighthouse CI (in CI pipeline, not just manual checks) | Performance/accessibility/best-practices/SEO scores gated per PR on key routes (landing, dashboard), validating the SEO architecture in Document 2 §6.4 is actually implemented correctly |

### 16.4 ML Model Testing & Validation (distinct from software testing)

This is a category most "production-ready" checklists miss — model correctness is not the same as code correctness:

```
1. Backtesting: walk-forward validation (train on data up to T, predict T+horizon,
   compare to actual, roll forward) — never a single train/test split for time
   series, which leaks future information and overstates accuracy.

2. Baseline comparison: every model must beat a naive baseline (e.g., "tomorrow's
   price = today's price" for 1-day horizon, or sector-average return) to be
   considered viable at all — prevents shipping a sophisticated model that's
   secretly worse than doing nothing. This requirement now explicitly EXTENDS to
   the stacking meta-model itself (Document 4 §10.2a) — the stacked ensemble must
   beat the single best-performing base model on held-out data, not just beat the
   naive baseline, closing a validation gap identified in review.

3. Directional accuracy tracked separately from magnitude error: for investment
   decisions, "predicted price is close but wrong direction" is a materially
   different failure than "right direction, price magnitude slightly off" — both
   RMSE/MAE (magnitude) and directional accuracy % (up/down correctness) are
   reported, never just one.

4. Drift monitoring: feature distributions and prediction accuracy are tracked
   over time in production. REVISION (gap identified in review): the original
   description here covered only LAGGING accuracy-drop detection via the
   `actualPrice` backfill process. Document 4 §10.8a now additionally specifies
   LEADING feature-distribution drift detection (PSI-based), paged as a monitoring
   alert (Document 5 §14.4) rather than left to a "weekly review."

5. Bias/fairness check specific to this domain: model performance is validated
   across market regimes (bull/bear/sideways) and across sectors/market-caps —
   a model that only works well for large-cap tech in a bull market is not
   "production ready" even if its aggregate historical metric looks good.

6. Sparse-data validation (gap identified in review — added): models/signals are
   additionally tested against instruments with minimal history (simulating a
   new IPO scenario) to verify the minimum-data gating in Document 4 §10.1a
   actually excludes the right models rather than silently running them on
   insufficient input — a dedicated fixture set with deliberately short history
   windows exercises this path in CI.
```

### 16.5 Test Data Strategy

- Unit/integration tests use deterministic fixtures (factory functions, e.g. `PortfolioFactory.build(holdings=[...])`), never live API calls to real vendors in CI.
- A recorded fixture set of real (but historical, publicly known) market data is checked into `tests/fixtures/` for reproducible ML pipeline tests — never randomly generated fake OHLCV data for ML tests specifically, because unrealistic synthetic price series can hide bugs that only manifest on real market data's actual statistical properties (fat tails, volatility clustering).
- Vendor API calls are mocked via `respx`/`responses` (Python) in all automated tests — CI never makes real network calls to Polygon/Alpha Vantage, both for speed/determinism and to avoid burning API quota on every CI run.
- **Staging environment data (missing entirely from the original draft — added per architecture review):** this section previously covered only automated *test* fixtures, never what data actually populates the running Staging *environment* (Document 7 §17.1 names the environment but never specifies this — a real gap, since an undecided staging data strategy creates two failure modes: staging with unrealistic toy data, or someone eventually copying real production data into it, which would violate §15.7's GDPR/CCPA posture). **Fix:** pre-launch, staging is populated by a synthetic seeding script (`scripts/seed-staging.ts`, faker-generated users/portfolios/transactions at a realistic volume). Post-launch, if production-representative staging data becomes necessary, it is sourced via a production-snapshot anonymization pipeline (email → `user{id}@example.test`, name → faker-generated, password hash → a fixed non-functional dev value, financial amounts optionally jittered) — tracked as a Phase 10 hardening item (Document 8 §24), not left undecided indefinitely.

### 16.6 CI Gate (what must pass before merge — enforced, not aspirational)

```
1. Lint (ruff for Python, eslint for TS) — zero errors
2. Type check (mypy --strict for Python, tsc --noEmit for TS against freshly
   regenerated packages/types — §16.2's BFF↔service contract check) — zero errors
3. Unit tests — 100% pass, coverage threshold met
4. Integration tests — 100% pass
5. Build succeeds (Docker images build, Next.js production build succeeds)
6. Security scan (dependency vulnerabilities — fail on High/Critical)
7. Smoke-tier E2E (3-5 critical-path tests, §16.3) — every PR, not main-only
   (gap identified in review: a broken critical path could previously sit
   undetected on `develop` until a `main` merge triggered the full E2E suite)
8. (main branch only) Full E2E suite against a deployed preview environment
9. (Phase 6+, main branch only) Resilience/chaos suite (§16.2a)
```

---

*End of Document 6. Continuing in Document 7: DevOps, CI/CD, Docker, Deployment, Scalability, Performance Optimization.*
