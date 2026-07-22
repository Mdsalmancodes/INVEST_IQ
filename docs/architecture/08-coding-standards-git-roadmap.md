# INVEST IQ — Architecture Blueprint
## Document 8 of N (Final): Coding Standards, Git Workflow, Naming Conventions, Documentation Standards, Development Roadmap (Phase 1–10)

> Status: DRAFT — pending founder approval

---

## 20. Coding Standards

### 20.1 TypeScript/Frontend Standards

```
- Strict mode enabled platform-wide: "strict": true in every tsconfig.json,
  no exceptions, no per-file "@ts-ignore" without a linked comment explaining why.
- No `any` — use `unknown` + narrowing, or generics. Enforced via
  @typescript-eslint/no-explicit-any as an error, not a warning.
- Explicit return types on all exported functions (not inferred) — improves
  readability and catches accidental type-widening at the boundary.
- Prefer type inference for local variables (don't annotate `const x: string = "a"`,
  the type is obvious) — annotate only at function boundaries and ambiguous cases.
- Interfaces for object shapes that might be extended/implemented; `type` for
  unions, intersections, and everything else — consistent, not arbitrary.
- No default exports except for Next.js page/layout files (which require it) —
  named exports everywhere else for better refactor/auto-import tooling support.
- All async operations use async/await, never raw .then() chains (readability
  + consistent error handling via try/catch).
- Component props always destructured in the function signature, always typed
  via an explicit `Props` interface (not inline unless trivially small).
```

### 20.2 Python/Backend Standards

```
- Full type hints on every function signature, checked via mypy --strict in CI.
- Pydantic models for all data crossing a boundary (API request/response, config,
  message queue payloads) — never raw dicts passed between layers.
- Domain entities are NOT Pydantic models — they are plain dataclasses or
  attrs classes with their own validation logic in __post_init__, deliberately
  decoupled from any serialization framework (Pydantic is an infrastructure/
  presentation-layer concern, the domain layer must not import it, this is the
  Dependency Inversion Principle applied concretely).
- Async-first: all I/O-bound functions (DB, HTTP, cache) are `async def`,
  using async drivers (asyncpg, motor, redis.asyncio) — sync blocking calls
  inside an async context are a banned pattern (they block the event loop).
- No bare `except:` — always catch specific exception types. No swallowing
  exceptions silently (a caught exception is always logged or re-raised,
  never both discarded and ignored).
- Ruff for linting/formatting (replaces Black + isort + flake8 — faster,
  single tool, single config).
- Docstrings (Google style) required on all public classes/functions in the
  domain and application layers (this is what "another team could build it
  from the docs alone" cashes out to at the code level, not just architecture
  documents).
```

### 20.3 SOLID in Practice (concrete platform examples, not abstract restatement)

```
Single Responsibility: GenerateForecastUseCase only orchestrates; it does not
  also contain feature engineering logic (that's FeatureEngineeringService) or
  persistence logic (that's ForecastRepository).

Open/Closed: Adding a new model family (e.g., a Transformer-based forecaster)
  means implementing a new class satisfying the `ForecastModel` protocol and
  registering it in the ensemble config — zero existing code is modified.

Liskov Substitution: Any `MarketDataProvider` implementation (Polygon, Alpha
  Vantage, yfinance) is fully interchangeable wherever the interface is used —
  swapping providers never requires the calling code to know which one it is.

Interface Segregation: `ForecastRepository` and `SentimentRepository` are
  separate protocols even though both might be backed by the same MongoDB
  connection — a consumer that only needs to read forecasts never depends on
  sentiment-writing capability.

Dependency Inversion: Application layer depends on repository Protocols
  defined in Domain; Infrastructure implements those protocols. The dependency
  arrow always points inward toward Domain, never outward toward Infrastructure.
```

### 20.4 DRY — Where It Applies and Where It Deliberately Doesn't

```
Applied: shared value objects (Money, Percentage, Ticker) live in
  libs/domain_common and packages/types, used identically across every
  service/app rather than redefined per-service.

Applied: validation schemas (Zod on frontend) are the single source of truth
  for form validation AND generate the OpenAPI-aligned types consumed by the
  typed API client — not maintained twice.

Deliberately NOT applied: each bounded context's domain entities are separate
  even if two contexts have superficially similar-looking fields (e.g.,
  Watchlist's simple symbol tracking vs. Portfolio's Holding) — collapsing
  these into one shared "Position" abstraction to avoid "duplication" would
  create false coupling between contexts that have genuinely different
  business rules and lifecycles. DRY applies to knowledge/logic duplication,
  not to structural similarity between unrelated concepts.
```

---

## 21. Git Workflow

### 21.1 Branching Model

```
main        — always production-deployable, protected, requires PR + passing CI + 1 approval
develop     — integration branch, auto-deploys to staging
feature/*   — feature/{ticket-id}-{short-description}, branched from develop
fix/*       — fix/{ticket-id}-{short-description}
hotfix/*    — branched from main directly, for production-critical fixes,
              merged to both main and develop
release/*   — (once release cadence stabilizes) release/{version}, cut from
              develop for final QA before merging to main
```

### 21.2 Commit Convention (Conventional Commits, enforced via commitlint in CI)

```
<type>(<scope>): <description>

feat(portfolio): add support for dividend transactions
fix(auth): correct refresh token expiry calculation
refactor(ai-service): extract SHAP explainer into dedicated service
test(watchlist): add integration tests for alert evaluation
docs(architecture): update database schema for corporate actions
chore(deps): bump fastapi to 0.115.0
perf(market-data): batch quote fetches to reduce vendor API calls
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `style`, `ci`. Scope is the affected module/service. Breaking changes flagged with `!` after type/scope (`feat(api)!: ...`) and a `BREAKING CHANGE:` footer.

### 21.3 PR Standards

```
- PR description template: What changed, Why, How tested, Screenshots (for UI),
  Rollback plan (for anything touching migrations/infra).
- Small, focused PRs preferred over large multi-concern PRs — a PR implementing
  a new feature and a PR fixing an unrelated bug are always separate.
- No direct pushes to main/develop — branch protection enforced at the repo level.
- All CI checks (Document 7 §18.2) must pass before merge is enabled.
- Squash-merge to keep main/develop history linear and readable; feature branch
  commit history can be messy during development, the squashed message follows
  the Conventional Commits format.
```

---

## 22. Naming Conventions

```
Files/folders (frontend):        kebab-case          stock-details-page.tsx
Files (Python):                   snake_case          generate_forecast_use_case.py
React components:                 PascalCase          PortfolioSummaryCard.tsx (default export
                                                        name matches file name)
TypeScript types/interfaces:      PascalCase          interface PortfolioSummary { }
TypeScript functions/variables:   camelCase           calculatePortfolioValue()
Python classes:                    PascalCase          class GenerateForecastUseCase
Python functions/variables:        snake_case          def calculate_portfolio_value()
Database tables:                   snake_case, plural   portfolios, watchlist_items
Database columns:                  snake_case           average_cost, created_at
API routes:                        kebab-case, plural    /api/v1/paper-orders
Environment variables:             SCREAMING_SNAKE_CASE  DATABASE_URL, JWT_SECRET
Redis keys:                        colon-namespaced      quote:AAPL, session:{userId}:permissions
CSS/Tailwind custom classes:       kebab-case (rare —    .glow-card-hover
                                    Tailwind utility-first
                                    means custom classes
                                    are the exception)
Git branches:                      kebab-case, prefixed  feature/inv-142-add-sip-calculator
Celery task names:                 dotted namespace       market_data.backfill_symbol,
                                                            ml.generate_forecast
```

---

## 23. Documentation Standards

```
- Every service has a README.md: purpose, local setup, how to run tests,
  how to run migrations, key architectural decisions specific to that service
  (linking back to this blueprint for cross-cutting concerns, not repeating it).
- Architecture Decision Records (ADRs) in docs/architecture/adr/ for any decision
  that reverses or significantly extends this blueprint post-approval — format:
  Context, Decision, Consequences, Alternatives Considered. This blueprint is
  the baseline; ADRs are the changelog of deviations as the system evolves.
- OpenAPI spec auto-generated from FastAPI (never hand-written, always in sync
  with actual code) — this is the API contract of record, consumed to generate
  the frontend's typed client (packages/types).
- Inline comments explain WHY, not WHAT (the code already says what it does;
  a comment restating that is noise — a comment is warranted when the reasoning
  isn't obvious from the code alone, e.g. "using historical simulation VaR
  instead of parametric because returns are fat-tailed, see Document 4 §10.5").
- Storybook for every component in packages/ui — serves as both visual
  documentation and the basis for visual regression testing (Document 6 §16.3).
```

---

## 24. Development Roadmap — Phase 1 to Phase 10

This is the build sequence. Each phase produces a genuinely working, demoable increment — never a phase that's "half a feature." Phases are sequential in priority but some internal parallelization is noted where frontend/backend work can proceed concurrently against an agreed contract.

### Phase 1 — Foundation & Skeleton
```
Goal: Monorepo scaffolded, every service boots, health checks pass, CI green.
- Monorepo setup (pnpm workspaces/turborepo + Python services as separate
  poetry projects), folder structure exactly as Document 2 §5.
- Docker Compose local environment: Postgres, Mongo, Redis, all 4 backend
  services (empty shells with /health endpoints), Next.js app (empty shell).
- CI pipeline skeleton (lint/typecheck/build stages green on empty apps).
- Shared libs scaffolded: libs/domain_common, packages/types, packages/validation,
  packages/ui (with design tokens from Document 2 §6.3 wired into Tailwind config).
- Base design system: Storybook running, core primitives (Button, Card, Input,
  Dialog) built to spec (Document 2 §6.3), dark/light considerations per palette.
Demo: docker-compose up brings up the full stack, all health checks green,
      a bare Next.js page renders using the design system's Button component.
```

### Phase 2 — Identity & Access
```
Goal: Real authentication, end to end.
- Postgres schema: users, oauth_accounts, refresh_tokens, audit_logs (Document 3 §8.1).
- core-api: register, login, refresh, logout, OAuth (Google) — full flow per
  Document 3 §7.4, bcrypt, JWT issuance, refresh rotation.
- Frontend: features/auth (LoginForm, RegisterForm, OAuth buttons), session
  handling, protected route middleware.
- RBAC scaffolding: role column, require_role()/require_ownership_or_role()
  dependency guards (Document 3 §7.5) — even though only `user` role is
  meaningfully used yet, the mechanism is built and tested now.
- Security headers, rate limiting on auth endpoints (Document 6 §15.2, §15.5).
Demo: A real user can register, verify session persistence across refresh,
      log out everywhere, and OAuth-login with Google.
```

### Phase 3 — Market Data Foundation
```
STATUS NOTE (post-Phase-2, founder-directed resequencing): the founder
explicitly directed that Portfolio Management (originally scoped to Phase 4
below) be built as "Phase 3" immediately after Authentication, ahead of this
Market Data Foundation phase. This is a SEQUENCING change, not an
architecture change — every table/entity/endpoint Portfolio Management
needs was already specified below (in what this document calls Phase 4) and
was built exactly as specified there, plus one additive schema extension
(ADR-0003: split/transfer_in/transfer_out transaction types). What's
DIFFERENT from originally planned: Portfolio's `holdings`/`transactions`
foreign-key into `instruments`, so a MINIMAL subset of this Market Data
Foundation phase's `instruments` table (schema only, per Document 3 §8.1,
no ingestion pipeline) was created ahead of schedule as a dependency — see
apps/core-api/src/infrastructure/persistence/postgres/portfolio_models.py's
module docstring.

STATUS UPDATE (Market Data Foundation phase — COMPLETE, see
docs/phase-4/verification-report.md for full evidence): the full scope below
(ohlcv_bars, corporate_actions, yfinance/Alpha Vantage providers, ingestion
pipeline, instrument search/quote/bars/corporate-actions endpoints,
stock-details frontend) is now built and verified, with these disclosed
deviations from the original plan (each with an upgrade path, none requiring
an ADR since none change a contract or remove architecture): `fundamentals`
endpoint NOT built (no schema/consumer for it yet, out of founder's explicit
Phase 4 list); `ohlcv_bars` built as a single non-partitioned table, not
partitioned from day one (no partition-maintenance job exists yet — see
Document 3 §8.1 annotation); Mongo raw-snapshot persistence and Redis
Pub/Sub event publishing (ingestion pipeline stages 4b/5) deferred (no
Mongo/consumer exists anywhere in this codebase yet — see Document 5 §11.2
annotation); a NEW `GET /market/status` endpoint was added (not in the
original catalog, an explicit founder requirement); Portfolio's
`PriceProvider` is no longer the `NullPriceProvider` stub — it is now
`RealPriceProvider`, backed by real OHLCV data, exactly per the upgrade path
this note previously described, with zero changes to
`PortfolioCalculationService` or any Portfolio use case.

Goal: Real (delayed-tier) market data flowing into the platform.
- core-api market-data module: MarketDataProvider interface + yfinance provider
  (dev) + Alpha Vantage provider (staging/prod-ready), ProviderRouter (Document
  5 §11.1). [REVISED: this is now a module within core-api, not a separate
  service, per Document 3 §7.1's post-review service collapse.]
- Postgres: instruments (with globally-unique-symbol partial index) — MINIMAL
  SUBSET ALREADY CREATED in the Portfolio Management work, see status note
  above; ohlcv_bars, corporate_actions — full DDL per Document 3 §8.1 revision,
  BUILT (ohlcv_bars non-partitioned, disclosed above). Ingestion pipeline
  (Document 5 §11.2): fetch → validate/dedupe → normalize → persist (Postgres
  half) → publish (deferred, disclosed above).
- Historical backfill: implemented as an on-demand SYNCHRONOUS fetch inline in
  GetOhlcvBarsUseCase on a coverage gap (not an enqueued Celery job with a
  backfill:inflight dedupe flag) — see Document 5 §11.3 annotation. A separate
  Celery task (sync_instrument_bars) exists for scheduled/proactive background
  sync, independent of this on-demand path.
- core-api: instrument search, quote, bars (OHLCV), prices (adjusted-close
  line-chart data — a deliberate split from a single combined "bars" endpoint,
  see Document 4 annotation), corporate-actions, and market/status endpoints.
  fundamentals NOT built (disclosed above).
- Frontend: features/market-data with a real price chart (TradingView
  lightweight-charts wrapper — OhlcvChart candlestick + PriceChart line),
  symbol search (StockSearch), live quote (LiveQuote), instrument detail page
  (InstrumentDetails) — built against the existing design-system tokens
  (including the success/danger gain-loss coloring added in Phase 3). Pages
  live at /markets (public, outside /dashboard's auth gate) per the backend's
  disclosed unauthenticated design — see Document 4 annotation.
Demo: Search for a real stock (e.g., AAPL), see its real historical chart and
      last-known quote (delayed, honestly labeled via `source`/
      `is_stale_fallback` fields in the UI), on both a desktop viewport and a
      375px mobile viewport, in both light and dark theme.
```

### Phase 4 — Portfolio & Watchlist Core
```
STATUS: Portfolio Management (the majority of this phase) was built and
verified as "Phase 3" per the founder's explicit resequencing direction —
see the status note under Phase 3 — Market Data Foundation above. What
remains of THIS phase's original scope: Watchlist (watchlists/
watchlist_items/alerts tables and CRUD, not yet built), and the live-quote
polling/valuation-update piece specifically (blocked on the real
Market Data Foundation phase's PriceProvider implementation, not on
anything Portfolio-side — Portfolio's calculation service already handles
a missing price source gracefully via holdings_missing_price).

STATUS UPDATE (Watchlist — COMPLETE, built as "Phase 5" per the founder's
explicit resequencing direction, see docs/phase-5/verification-report.md
for full evidence): watchlists/watchlist_items built and verified, PLUS
ADR-0004's additive multi-watchlist/default-watchlist/custom-ordering/
pinning support (exceeding this section's original minimal scope, which
only specified "watchlists" as one line item with no ordering/pinning
detail). `alerts` table and its CRUD were NOT built in this pass — alerts
remain future scope, genuinely out of the founder's explicit Phase 5
Watchlist requirement list. The "live-quote polling/valuation-update"
blocker noted above is now resolved for Watchlist specifically:
WatchlistEnrichmentService (new, Phase 5) calls Phase 4's
GetCurrentPriceUseCase/GetMarketStatusUseCase directly — no additional
blocker remained once Market Data Foundation (this document's Phase 3)
landed. Frontend: features/watchlist built (WatchlistDashboard/Cards/
Table/dialogs), reusing Phase 4's StockSearch/LiveQuote/PriceChart
components rather than duplicating chart/search UI, at
apps/web/app/dashboard/watchlists/{page.tsx,[id]/page.tsx}.


Goal: Users can track real (paper) holdings and watch symbols.
- Postgres: portfolios, holdings, transactions, watchlists, watchlist_items,
  alerts (with the duplicate-alert unique constraint, Document 3 §8.1 revision).
- Domain layer: Portfolio aggregate with apply_transaction() logic (average
  cost basis calculation, quantity invariants — Document 3 §3.4 rule #1 and #2).
- core-api: full CRUD for portfolios/holdings/transactions/watchlists.
- Frontend: features/portfolio (HoldingsTable using the DataTable composite's
  mobileRenderMode='card' pattern per Document 2 §6.1a, add-transaction flow,
  portfolio valuation using live quote cache), features/watchlist.
- Redis (`redis-cache` instance specifically, per the 3-way split) quote
  caching wired in for live-ish valuation updates (polling-based at this
  phase; WebSocket comes in Phase 6). Read-after-write consistency rule
  (Document 3 §7.7) applied from this phase since it's the first phase with
  meaningful write-then-read-own-data flows.
Demo: Create a portfolio, add a real holding (e.g., 10 shares of AAPL at cost),
      see live-updating portfolio value as the market price changes, verify
      the holdings table renders as stacked cards on a mobile viewport.
```

### Phase 5 — Landing Page & Design Polish
```
Goal: The actual "billion-dollar startup" front door.
- Full landing page per Document 1 §1 layout: Hero (3D AI Brain via R3F or
  Spline embed, per Document 2 §6.6 performance rules), Features, How AI Works,
  Screenshots, Pricing (static/future-ready), FAQ, Footer.
- SEO architecture implemented per Document 2 §6.4: generateMetadata() with
  dynamic OG images, JSON-LD structured data, sitemap.ts, robots.ts — built
  now while the landing page is being built, not bolted on afterward.
- Animation pass: Framer Motion micro-interactions, GSAP hero choreography,
  animated counters, magnetic buttons, glow effects — governed strictly by
  the performance rules in Document 2 §6.6 (dynamic imports, PLATFORM-WIDE
  reduced-motion fallback per §6.5, one 3D scene max, measurable ≥50fps target).
- Lighthouse CI gate active from this phase onward (Document 6 §16.3) —
  the landing page is the first thing scored (performance/accessibility/SEO)
  and must meet the bar before later phases add more surface area to optimize.
Demo: The landing page, on both a high-end and a throttled/low-end device
      profile (via Chrome DevTools throttling), loads fast and looks premium;
      verify a shared link renders a correct dynamic OG preview card.
```

### Phase 6 — Real-Time Layer
```
Goal: Live data actually feels live.
- core-api notification module stood up: WS connection handling, Redis
  Pub/Sub subscriber pattern, graceful-shutdown reconnect-advised frames,
  client-side exponential-backoff reconnection (Document 3 §7.6, all revised
  post-review). [REVISED: module within core-api, not a separate service.]
- core-api market-data module: streaming provider support (if Pro-tier vendor
  key available) or tightened polling interval for delayed tier, publishing
  QuoteUpdated events.
- core-api: /realtime/token endpoint (short-lived WS connect tokens), per-user
  and per-IP concurrent connection caps (Document 3 §7.6 revision).
- Frontend: WebSocket client with reconnection/backoff logic, useLiveQuote hook
  bridging WS messages into React Query cache (Document 2 §6.2), ARIA live
  region announcements for price changes per the accessibility standard
  (Document 2 §6.5) — dashboard/watchlist/stock-details now update without
  polling/refresh.
- Alerts: Postgres alerts table (with duplicate-prevention constraint), sharded
  Redis Streams-based evaluation engine (Document 3 §7.8 revision), alert
  CRUD API + UI.
- Resilience/chaos test suite (Document 6 §16.2a) gated as a required check
  for this phase — consumer-crash, slow-client backpressure, Redis
  disconnect/reconnect, and graceful-shutdown scenarios all verified, not
  just the happy path.
Demo: Open the watchlist in two browser tabs, see prices update live in both
      simultaneously without refresh; set a price alert and receive an
      in-app notification when triggered; kill a core-api instance mid-session
      and verify the client reconnects automatically without user action.
```

### Phase 7 — AI/ML Core: Prediction & Sentiment
```
Goal: The actual "AI" in AI Powered Investment Intelligence, working honestly.
- ai-service stood up: feature engineering pipeline using the shared feature
  registry library (Document 4 §10.2 revision — libs/domain_common/features/
  registry.py, imported identically by training and inference) writing to
  Mongo feature_snapshots with featureSetVersion tracking.
- Model training pipeline (ml/training/): LSTM, Prophet, ARIMA, XGBoost/LightGBM/
  CatBoost trained on real historical data pulled from Phase 3's ingestion.
  Backtesting harness (Document 6 §16.4) built alongside — models are validated
  against a naive baseline before being considered for serving. Minimum-data
  gating (Document 4 §10.1a) implemented and tested against sparse-history
  fixtures (simulated new-IPO scenario) from this phase, not deferred.
- Ensemble inference service + concretely-specified stacking meta-model
  (Document 4 §10.2a) + per-member inference timeout/partial-ensemble
  handling + SHAP explainability (§10.9) — PredictionRun persisted immutably
  to Mongo with dataQuality field populated.
- Sentiment pipeline: news ingestion, FinBERT scoring, volume-weighted
  aggregation (Document 4 §10.3 revision).
- ai-service degraded-mode contract (Document 4 §10.1b) implemented from this
  phase: core-api's MockAiServiceClient (used in local dev per Document 7
  §17.4) has a real production counterpart — the actual degraded-response
  path is exercised, not just mocked away in dev.
- Frontend: features/predictions (ForecastCard, ConfidenceGauge, ShapExplainer
  waterfall chart with keyboard-navigable table fallback per Document 2 §6.5),
  features/sentiment, features/news.
- ModelVersion lifecycle with canary rollout_percentage + concept drift
  monitoring (Document 4 §10.8/§10.8a) — even if only one version exists
  initially, the mechanism is real and tested, including the auto-rollback path.
Demo: View a real stock's AI-generated price forecast with an honest confidence
      score and a SHAP explanation panel showing which factors drove the
      prediction; view aggregated sentiment for the same stock derived from
      real recent news; view a forecast for a deliberately short-history test
      symbol and confirm it's honestly flagged dataQuality: insufficientHistory
      rather than silently degraded.
```

### Phase 8 — Recommendation, Risk, Optimization, Paper Trading
```
Goal: Synthesis layer + actionable simulated trading + risk/portfolio science.
- Recommendation synthesis service (Document 4 §10.4): weighted scoring over
  Prediction + Sentiment + technical signal confluence + risk penalty,
  per-risk-profile weight configs (implemented via the feature flag service,
  Document 7 §19.3a, as its first concrete use case), full explainability
  breakdown persisted. Reads only pre-computed records per §9.4a's bound.
- Risk engine (Document 4 §10.5): volatility, VaR95 (historical simulation),
  Sharpe, beta, composite riskScore — computed nightly + on-demand, with
  covariance shrinkage fallback for sparse-history holdings (§10.1a).
- Portfolio optimizer (Document 4 §10.6): convex optimization (cvxpy/scipy)
  with concentration/sector constraints, bounded to ≤100 holdings with a 10s
  solver timeout, dispatched async via the ml-inference queue (§9.4a revision).
- Candlestick pattern detection (Document 4 §10.7) — rules engine, integrated
  into stock-details chart annotations; deliberately has no ai-service
  dependency, so it remains available during an ai-service outage (§10.1b).
- Paper trading: paper_orders table (with updated_at trigger + per-portfolio
  idempotency-key uniqueness, Document 3 §8.1 revision), order placement/fill
  simulation (market orders fill immediately at current quote; limit orders
  evaluated against the sharded alert-evaluation-style sweep), Idempotency-Key
  header enforcement (Document 4 §9.7).
- Frontend: features/risk-analysis, features/optimizer, features/paper-trading,
  Buy/Sell/Hold verdict badges integrated into stock-details and dashboard,
  all built against the DataTable mobile card pattern (Document 2 §6.1a).
Demo: View a full Buy/Sell/Hold recommendation with complete "why" breakdown;
      run the portfolio optimizer against a real (paper) portfolio and see a
      concrete rebalancing suggestion; place a paper trade and see it reflected
      in holdings and transaction history; kill ai-service and verify
      candlestick patterns still render while the Forecast panel shows a
      clear degraded-state message instead of erroring.
```

### Phase 9 — AI Assistant, Screener, Admin Panel, Notifications Polish
```
Goal: Conversational layer + remaining core pages + operability.
- AI Assistant: ConversationSession/AssistantMessage domain model, LLM
  integration with tool-calling into Portfolio/Market Data/Recommendation/Risk
  (Document 3 DDD §3.1 AI Assistant context), SSE streaming responses,
  per-user token budget + max tool-call-loop cap + LLM circuit breaker +
  tool-execution-boundary re-authorization (Document 4 §9.6a — all four
  cost/security controls implemented together, not deferred).
- Stock Screener: multi-factor filtering restricted to the pre-materialized
  screener_factors table (Document 3 §8.1 revision), 8-condition cap, Redis-
  cached results with stampede protection (Document 3 §7.7). Filter panel
  uses the mobile Sheet pattern below `md` (Document 2 §6.1a).
- SIP Calculator, IPO Analyzer, Dividend Analysis — now with real backing
  schema and endpoints defined in Document 3 §8.1 revision and Document 4
  §9.4 revision (sip_scenarios, ipo_listings, dividend_records tables;
  /sip/calculate, /ipo/listings, /portfolios/{id}/dividend-projection routes)
  rather than being named-but-unspecified as in the original roadmap draft.
- Admin Panel: user management, role changes, model-version promotion UI
  including the canary rollout_percentage control and rollback endpoint
  (Document 4 §10.8 revision), news source management, feature flag management
  UI (Document 7 §19.3a).
- Notification preferences UI, email delivery wiring (Celery task, Document 5 §12.2).
- Settings, Profile, full Notifications inbox pages.
Demo: Have a real conversation with the AI Assistant that correctly answers
      a question about the user's actual portfolio by calling platform tools,
      and confirm it refuses/is blocked from accessing another user's portfolio
      even when asked to; run the screener with real multi-factor filters;
      an admin promotes a new model version through a canary rollout and
      manually triggers a rollback; calculate a SIP projection for a real stock.
```

### Phase 10 — Hardening, Observability, Launch Readiness
```
Goal: Production-grade, not just feature-complete.
- Full test coverage push to meet thresholds (Document 6 §16.2-16.3) across
  both services — this phase is partly a "pay down any testing debt" pass.
  Resilience/chaos suite (§16.2a) and BFF↔service contract check (§16.2)
  both green and required, not optional.
- Monitoring/alerting stood up for real (Document 5 §14.4, extended by
  Document 4 §10.8a): Prometheus+Grafana dashboards, Sentry/GlitchTip error
  tracking, Celery queue monitoring, model concept-drift PSI alerting wired
  to page (not just "weekly review").
- Security pass: dependency audit, penetration-test-style review against the
  threat model (Document 6 §15.1, including the newly-added prompt-injection
  and algorithmic-complexity rows), header/CSP verification (including the
  Spline/embed-specific CSP directives), secrets rotation procedure executed
  once as a drill (§15.4 revision), not just theoretically available.
- Backup & disaster recovery drill (Document 3 §8.5 — missing entirely from
  the original roadmap): restore the most recent Postgres and MongoDB backups
  into an isolated environment, run the full integration suite against the
  restored data, confirm RPO/RTO targets are actually met, not just configured.
- Performance pass: Lighthouse scores finalized (including SEO, per Document 2
  §6.4), bundle size budget enforced, database query audit for N+1s, load
  testing key endpoints (portfolio valuation, quote streaming, prediction
  serving, screener) under realistic concurrent load — including a deliberate
  cache-stampede scenario (many concurrent requests for a newly-invalidated
  popular symbol) to verify the distributed-lock protection (Document 3 §7.7)
  actually holds under load, not just in isolated tests.
- CI/CD production deployment pipeline finalized (Document 7 §18.3), rollback
  tested (deliberately trigger a failed health check in staging, verify
  automatic rollback works).
- Accessibility audit (WCAG 2.1 AA) across all primary pages, verifying the
  component-level design requirements in Document 2 §6.5 (not just automated
  axe-core scan results) — manual screen-reader pass on the live price ticker
  and chart fallbacks specifically, since these are the highest-risk surfaces.
- Documentation finalization: every service README complete, ADRs for any
  deviations from this blueprint during implementation, OpenAPI spec reviewed.
- Legal/compliance content: Terms of Service, Privacy Policy, and the
  "not financial advice" disclaimer verified present on every ML-derived
  surface (Document 4 §9.2) — engineering-verifiable via an automated test
  that asserts the disclaimer field is non-null on every recommendation/
  forecast API response.
Demo: A full walkthrough of every page in the platform under production-like
      conditions (real deployed environment, not localhost), with monitoring
      dashboards showing real request traces, and a demonstrated rollback drill.
```

### 24.1 Cross-Cutting Note on Parallelization

Within each phase, frontend and backend work for that phase's features can proceed in parallel once the API contract (OpenAPI schema + DTOs) for that phase is agreed — frontend builds against a mocked API (MSW, per Document 6 §16.3) while backend implements the real thing, integrating once both are ready. This is a process note for whoever staffs the build, not a phase itself.

---

## 25. Summary — What Approval Unlocks

This 8-document blueprint (Documents 1–8, covering Product/System/DDD architecture, Clean Architecture/Folder Structure/Frontend, Backend/Database, API/AI-ML Pipeline, Data Engineering/Notifications/Caching/Monitoring, Security/Testing, DevOps/CI-CD/Deployment/Scalability, and Coding Standards/Roadmap) is saved in full under:

```
investiq/docs/architecture/
├── 01-product-and-system-architecture.md
├── 02-clean-architecture-folder-frontend.md
├── 03-backend-architecture-database-design.md
├── 04-api-design-ai-ml-pipeline.md
├── 05-data-pipeline-notifications-caching-monitoring.md
├── 06-security-testing-strategy.md
├── 07-devops-cicd-deployment-scalability.md
└── 08-coding-standards-git-roadmap.md   (this document)
```

Per your original instruction, no implementation code has been written. Upon your approval, build proceeds **one production-ready module at a time**, starting with Phase 1 (Foundation & Skeleton), and each subsequent module will be built to the standards fixed in this blueprint — not reinterpreted per-feature.

**Awaiting your review and approval before implementation begins.**
