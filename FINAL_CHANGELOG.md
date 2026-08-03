# Final Changelog

This changelog summarizes what has been built, phase by phase, based on
`docs/phase-*/` (the authoritative implementation record — see
`FINAL_REPOSITORY_REVIEW.md` §5 for why the architecture blueprint's own
roadmap document is not used as the source here), followed by this
repository-cleanliness pass's own changes.

## Phase 1 — Foundation & Skeleton

Initial monorepo scaffold: `apps/web` (Next.js 15), `apps/core-api` and
`apps/ai-service` (FastAPI), `packages/ui`/`packages/config`, `libs/*`
Python shared libraries, Docker Compose orchestration, CI-shaped tooling
(lint/typecheck/test scripts). Environment-specific fixes recorded for
Windows-native local development.

## Phase 2 — Authentication Module

JWT-based authentication: registration, login, refresh tokens, password
reset flow. Frontend login/register/forgot-password forms with client-side
validation (Zod schemas, `packages/validation`).

## Phase 3 — Portfolio Management

Portfolio CRUD, transaction recording (buy/sell/dividend/split/transfer),
holdings calculation, portfolio summary (total investment, P&L, realized/
unrealized gain). ADR-0003 (split/transfer transaction types) and
ADR-0002 (login history table) recorded during this phase.

## Phase 4 — Market Data Foundation

OHLCV bar ingestion (yfinance provider, disclosed as a dev-only data
source), instrument search, current price/quote endpoints, historical
price series, corporate actions, market status. Background sync task via
Celery.

## Phase 5 — Watchlist

Multi-watchlist support per user, item pinning/reordering, live quote
enrichment (`WatchlistEnrichmentService`) reused later by Phase 9's
real-time layer. ADR-0004 (watchlist multi-list ordering/pinning) recorded.
Landing page and design system polish also delivered in this phase per the
root README's structure note.

## Phase 6 — Alerts & Notifications

Price/percentage-change/RSI-threshold alert conditions, cooldown logic,
notification delivery + preferences (email/push toggles, digest frequency,
quiet hours). Alert domain methods (`can_trigger_now()`/`trigger()`) built
here but not yet wired to any evaluation loop — disclosed as a known issue,
closed in Phase 9.

## Phase 7 — Hybrid AI & Machine Learning Engine

The 6-model ensemble (LSTM, ARIMA, Prophet, Random Forest, XGBoost,
FinBERT) combined via weighted voting into a single BUY/SELL/HOLD
`Recommendation` with confidence scoring and SHAP-based explainability.
Feature engineering pipeline, prediction history persistence
(`PredictionRun`), model training/retraining/versioning.

## Phase 8 — Enterprise Security

JWT refresh-token hardening, Role-Based Access Control (Admin/Premium/
Basic), an API Gateway pattern so `ai-service` is never directly reachable
from the browser (all AI calls proxied through `core-api`, enforced by an
internal shared-token header), rate limiting, request validation, security
headers, CORS, audit logging. Frontend: permission guards, protected
routes, session management, auto-logout, refresh-token handling.

## Phase 9 — Real-Time Market Intelligence

A single shared WebSocket connection per browser tab (backed by Redis
Pub/Sub) delivering live stock prices, live watchlist/portfolio updates,
live AI predictions/sentiment, and instant alert notifications. Closed the
Phase 6 known-issue by building the Alert Evaluation Engine that actually
calls `Alert.can_trigger_now()`/`trigger()`. New `sector_allocation`
aggregation for live portfolio views.

## Production Audit Pass (post-Phase 9)

A full security/performance/correctness audit across all three
applications, with fixes applied and verified:

**Backend (core-api):**
- Fixed a real bug: `sort_by`/`sort_direction` query parameters on alert/watchlist list endpoints were typed as plain `str` with a bypassed type check, letting an invalid value cause an uncaught `KeyError` → 500 instead of a clean 422. Now properly typed as `Literal`s.
- Removed an insecure default value for `internal_service_token` (was silently usable if unset; now a required `SecretStr` with no default, matching `jwt_secret`'s fail-fast pattern).
- Fixed a connection-pooling bug: the AI proxy's HTTP client was being created and torn down on every single request instead of reused across the process lifetime.
- Fixed an N+1 pattern in watchlist enrichment (sequential per-item quote lookups → concurrent `asyncio.gather`).
- Added a missing database index on `alerts.user_id` (the only per-user resource table missing one).
- Normalized a background task's transaction-commit handling to use the same centralized session-scope helper every other write path uses.

**Backend (ai-service):**
- Fixed the highest-value finding: the 5-model training/inference pipeline ran synchronously inside async request handlers, blocking the event loop for the full training duration on every request. Now offloaded via `asyncio.to_thread()`.
- Added per-model exception isolation so one model family's genuine failure no longer fails the entire ensemble.
- Added request-size bounds (DoS protection) on two previously-unbounded list inputs feeding synchronous batch inference.
- Added a NaN/inf guard on price forecasts before they reach the API response.
- Fixed a training-request validation gap (`family` field is now a proper `Literal`, returning 422 instead of 500 on invalid input).

**Frontend (web):**
- Added runtime (Zod) validation to three previously-unvalidated WebSocket payload consumers.
- Deferred the landing page's 3D visual scene (`three.js`/`@react-three/fiber`) via `next/dynamic`, removing it from the initial JS bundle for every visitor.
- Deduplicated a verbatim-duplicated HTTP client helper (`authorizedRequest`/`buildQueryString`) across 6 API client files into one shared module.
- Added root and dashboard-scoped error boundaries (previously absent — unhandled render errors fell through to Next's default error screen).
- Added `prefers-reduced-motion` support to both 3D scenes.
- Added SEO metadata (`openGraph`/`twitter`/`metadataBase`/`viewport`), `sitemap.ts`, and `robots.ts`.
- Various smaller accessibility/consistency fixes (missing `aria-label`, responsive chart heights, stale code comments).

## Repository Cleanliness Pass (this document's own scope)

No functionality changed. See `FINAL_REPOSITORY_REVIEW.md` for full detail.

- Removed 21 stray tracked debug/scratch files (ad-hoc log dumps, a TypeScript
  build-cache file, a Playwright run-state cache, 17 leftover model-training
  scratch artifacts).
- Closed the `.gitignore` gaps that had let those files get committed in the
  first place, plus added rules for `.tsbuildinfo`, `test-results/`,
  `playwright-report/`, and (going forward) `.localdev/`.
- Corrected `README.md`'s structure diagram and status section to match
  what actually exists/has been built, rather than the original plan.
- Refreshed `apps/core-api/.env` and clarified `apps/web/.env.example` to
  match their current, real configuration surface.
- Flagged (but did not unilaterally act on) `.localdev/`'s git-tracking
  status — 20,392 files including vendored binaries and plaintext-looking
  credentials — as requiring the repository owner's explicit decision.
- Generated this document plus `FINAL_REPOSITORY_REVIEW.md`,
  `PROJECT_STRUCTURE.md`, and `DEPLOYMENT_GUIDE.md`.
