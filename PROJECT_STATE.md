# INVEST IQ — Project State

**Last updated:** Phase 9 completion (Real-Time Market Intelligence).
**Monorepo:** `apps/core-api` (FastAPI/SQLAlchemy 2/Alembic/PostgreSQL/Redis), `apps/ai-service` (FastAPI + ML stack), `apps/web` (Next.js 15/React 19), `packages/ui`, `packages/validation`, `packages/config`.

This document is a single-page summary of every phase's status, refreshed at the end of each phase. For full detail on any phase, see `docs/phase-N/`.

## Phase Status Summary

| Phase | Scope | Status | Backend tests | Frontend tests | ADRs |
|---|---|---|---|---|---|
| 1 | Infrastructure skeleton (core-api, ai-service, web scaffolding, Docker Compose, CI shape) | ✅ Complete | N/A (skeleton) | N/A (skeleton) | ADR-0001 (Python 3.11 local dev) |
| 2 | Authentication (register/login/refresh/logout/password reset/email verification) | ✅ Complete | 105 (97 executable + 8 integration written-not-executed) | 37 unit + 8 E2E | ADR-0002 (login_history table) |
| 3 | Portfolio Management (CRUD, 8 transaction types, 10 calculations) | ✅ Complete | Cumulative growth documented in phase report | Cumulative growth documented in phase report | ADR-0003 (split/transfer transaction types) |
| 4 | Market Data Foundation (providers, OHLCV, corporate actions, Celery sync, Portfolio real-price integration) | ✅ Complete | Cumulative growth documented in phase report | Cumulative growth documented in phase report | ADR-0002, ADR-0003 ratified to Accepted |
| 5 | Watchlist (multi-list, pinning, ordering, live enrichment) | ✅ Complete | Cumulative growth documented in phase report | Cumulative growth documented in phase report | ADR-0004 (watchlist multi-list/ordering/pinning), Accepted |
| 6 | Alerts & Notifications (CRUD alerts, notifications list/read, preferences) | ✅ Complete | 401 passing, 55 deselected (Docker unavailable) | 169 unit + 20 E2E | None required |
| 7 | Hybrid AI & Machine Learning Engine (6 models, Decision Engine, SHAP, full API, frontend dashboard) | ✅ Complete | ai-service: 193 passing; core-api regression: 401 passing, 55 deselected | 118 unit + 21 E2E | None required |
| 8 | Enterprise Security (RBAC, AI Gateway/proxy, Redis token blacklist, rate limiting, security headers/CORS/CSRF/SQLi/XSS, audit logging, API versioning policy, frontend permission guards/session management) | ✅ Complete | core-api: 459 passing, 55 deselected; ai-service: 202 passing | 156 unit + 18 E2E (+4 pre-existing, disclosed, non-Phase-8-related failures) | None required |
| 9 | Real-Time Market Intelligence (WebSocket infrastructure, Redis Pub/Sub, live stock/watchlist/portfolio/AI-prediction/sentiment streaming, Alert Evaluation Engine + instant push, frontend real-time dashboards with animated transitions/toasts/connection indicators) | ✅ Complete | core-api: 554 passing, 55 deselected; ai-service: 202 passing (untouched) | 181 unit + 21 E2E (+4 pre-existing, disclosed, non-Phase-9-related failures) | None required |

**Cumulative test count at end of Phase 9:**
- **core-api**: 554 tests passing, 55 integration tests written-but-unexecuted (Docker unavailable throughout the project's history in this environment).
- **ai-service**: 202 tests passing (unchanged from Phase 8 — Phase 9's Live AI/Live Sentiment features go through the existing Phase 8 proxy client with zero ai-service-side changes).
- **apps/web unit**: 181 tests passing (41 test files).
- **apps/web E2E**: 21 tests passing (Playwright, run against `next dev` — production `next build`'s standalone-output step is blocked by a Windows-specific `EPERM` symlink issue, documented since Phase 1), plus 4 pre-existing/disclosed failures unrelated to Phase 9 (see `docs/phase-9/known-issues.md` D2, same 4 tests originally disclosed in Phase 8's known-issues.md D3).
- **packages/ui**: 4 tests passing, unchanged baseline.
- **Grand total**: 962 individual test executions across the whole monorepo passing, zero known regressions to any completed phase.

## Bounded Contexts Implemented

| Context | Backend location | Auth | Notes |
|---|---|---|---|
| Auth | `core-api/src/domain/auth/` et al. | N/A (issues auth) | JWT access + refresh, argon2 password hashing, Phase 8: jti-based Redis blacklist added alongside the existing token_version blanket-revocation mechanism |
| Portfolio | `core-api/src/domain/portfolio/` et al. | Authenticated | Aggregate root pattern, Decimal-everywhere discipline, Phase 8: optional large-transaction audit logging, Phase 9: live WebSocket streaming + sector allocation layered on top of the frozen calculation service |
| Market Data | `core-api/src/domain/market_data/` et al. | **Public/unauthenticated** (disclosed design) | Provider abstraction + failover, Celery background sync, Phase 9: a new polling loop publishes live quote ticks to Redis for WebSocket fan-out (the existing GetCurrentPriceUseCase/GetMarketStatusUseCase remain unmodified) |
| Watchlist | `core-api/src/domain/watchlist/` et al. | Authenticated | Reuses Market Data's live-quote use cases via Protocol injection, Phase 9: live WebSocket streaming re-runs the existing enrichment service on a timer for subscribed users |
| Alerts | `core-api/src/domain/alerts/` et al. | Authenticated | CRUD, **Phase 9: the Alert Evaluation Engine was built** — `Alert.can_trigger_now()`/`trigger()` are now finally called, closing the standing Phase 6/7/8 known-issue. Only price_above/price_below/pct_change/rsi_threshold conditions are evaluated; portfolio-threshold/prediction-change/sentiment-change remain unimplemented (see `docs/phase-9/known-issues.md` B2) |
| Notifications | `core-api/src/domain/notifications/` et al. | Authenticated | In-app only — no email/push delivery path yet (Phase 6 known-issues B2), Phase 9: alert-triggered notifications now push instantly over WebSocket in addition to the existing REST list/read-state model |
| AI/ML (`ml`) | `ai-service/src/domain/ml/` et al. | **Internal-only, service-to-service** (Phase 8 — `InternalServiceAuthMiddleware` rejects any request lacking core-api's internal token) | 6 models + Decision Engine + SHAP; not directly reachable by the frontend (Phase 7's A1/A2 gap, closed Phase 8). Phase 9: entirely untouched — Live AI/Live Sentiment streaming goes through the existing AiServiceClient proxy exclusively |
| AI Proxy (`ai_proxy`) | `core-api/src/application/ai_proxy/`, `presentation/routers/ai_proxy_router.py` | Authenticated (any role for read endpoints; Admin/Super Admin only for model status/train/retrain/delete) | The API Gateway pattern for all AI/ML access (Phase 8); Phase 9's AiPredictionStreamingService/SentimentStreamingService reuse this exact client, never calling ai-service directly |
| Real-Time (`realtime`) | `core-api/src/infrastructure/realtime/`, `presentation/routers/realtime_router.py` | Authenticated (JWT via WS query-param token, reusing the existing JwtProvider/TokenBlacklist) | **New this phase** — the single WebSocket endpoint (`/api/v1/realtime/ws`) and 7 background services (RealtimeService + 6 streaming/evaluation services) bridging Redis Pub/Sub to connected clients. See `docs/phase-9/implementation-summary.md` for the full design |

## Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| 0001 | Python 3.11 local dev compatibility | Accepted |
| 0002 | `login_history` table | Accepted |
| 0003 | Split/transfer transaction types | Accepted |
| 0004 | Watchlist multi-list ordering/pinning | Accepted |

No ADR was required for Phase 6, 7, 8, or 9 — each phase implemented already-frozen architecture decisions or founder-instructed extensions, without reversing or deviating from any prior decision. See each phase's `verification-report.md`/`implementation-summary.md` for the explicit justification.

## Standing Known Issues (carried across phases)

These are re-confirmed, not newly discovered, at the end of every phase since Phase 1:

1. **Docker / Docker Compose not installed** in this development environment — blocks 55 written-but-unexecuted core-api integration tests and prevents any phase's E2E suite from exercising a genuinely running backend (all E2E tests verify client-side route-guard/rendering behavior against `next dev` only). Also means **no real Redis instance runs in this environment** — Phase 8's rate limiter and token blacklist, and now Phase 9's entire WebSocket/Redis Pub/Sub real-time layer, were all designed and tested against this constraint (fail-open on Redis unavailability; fakes in every unit test; see `docs/phase-9/known-issues.md` D1 for the fullest current writeup of this limitation's impact).
2. **Next.js `output: "standalone"` build fails on this Windows machine** (`EPERM` on symlink creation during file-tracing) — reproduced identically every phase since Phase 1; unrelated to any application code; Docker (Linux) is the intended authoritative build-verification path once available.
3. **No shared dashboard navigation shell** — every dashboard route (`/dashboard/portfolios`, `/dashboard/watchlists`, `/dashboard/alerts`, `/dashboard/notifications`, `/dashboard/ai`) is reachable only by direct URL or a link from wherever a future nav shell would eventually place them. Unchanged this phase.
4. **Market Data REST API is unauthenticated by design** (Phase 4's disclosed decision that reference data doesn't need per-user gating). The AI/ML REST API's equivalent gap (Phase 7's A1/A2) was closed in Phase 8 — ai-service is not directly reachable by the frontend at all.
5. **Refresh token still returns in the JSON response body, not an httpOnly cookie** (Phase 2's original disclosed limitation, re-confirmed still true through Phase 9) — this is also the reason CSRF protection was found to be structurally unnecessary rather than built in Phase 8 (`docs/phase-8/known-issues.md` B1/D2).
6. **Four pre-existing E2E test failures** (`auth.spec.ts` x3, `markets.spec.ts` x1) — investigated thoroughly during Phase 8, re-confirmed identically during Phase 9 (via `git status` and an isolated `--workers=1` re-run), unrelated to any Phase 8 or Phase 9 change, not yet resolved (see `docs/phase-9/known-issues.md` D2).
7. **The Alert Evaluation Engine only supports 4 of the 5 named trigger categories** (target price, stop loss, and %-change/RSI conditions are live; portfolio-threshold, prediction-change, and sentiment-change conditions are not implemented) — `Alert`'s domain model has no field or defined semantics for these three yet; see `docs/phase-9/known-issues.md` B2 for the full design-work-required explanation.
8. **True live news/social-media sentiment ingestion remains unbuilt** — Phase 9's live sentiment refresh reuses the AI recommendation's existing `sentiment_score` field rather than analyzing fresh text, since no live text-ingestion pipeline exists anywhere in this codebase (same underlying gap Phase 7 first disclosed for the on-demand SentimentDashboard); see `docs/phase-9/known-issues.md` B1.

## Recommended Next Phase

With Phase 9's Real-Time Market Intelligence work complete — WebSocket infrastructure, live streaming across stock data/watchlist/portfolio/AI predictions/sentiment, the Alert Evaluation Engine finally built and pushing instant notifications, and a fully live-updating frontend dashboard — candidates for the next phase, in priority order:
1. **Shared dashboard navigation shell** (carried forward from Phase 8's own recommendation, still unbuilt) — every dashboard route remains reachable only by direct URL; now an even stronger candidate given how many real-time-enabled dashboard sections exist.
2. **Portfolio-threshold / prediction-change / sentiment-change alert conditions** (Phase 9's own disclosed known-issue #7 above) — the Alert Evaluation Engine now exists and is proven working for 4 condition types; extending it to the remaining 3 requires genuine new domain design (does `Alert` need a `portfolio_id` field? what does "prediction changed" compare against?) rather than a mechanical extension.
3. **True live news/social-media sentiment ingestion** (known-issue #8 above) — building a real text-ingestion pipeline (news API, Reddit API, or similar) that `SentimentAnalysisUseCase` could actually run against on a schedule, closing the gap Phase 7 first disclosed and Phase 9 re-confirmed.
4. **BFF httpOnly-cookie refresh-token flow** — closing Phase 2's original disclosed interim, which would also be the trigger point for revisiting CSRF protection.
5. **Landing Page & Design Polish** — still independent of all backend feature work, still not started.
