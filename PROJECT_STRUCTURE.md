# Project Structure

This document describes the actual, current layout of the INVEST_IQ
monorepo as of this writing (verified against disk, not aspirational). For
the *rationale* behind this structure, see
`docs/architecture/02-clean-architecture-folder-frontend.md`.

## Top level

```
INVEST_IQ/
├── apps/                    Deployable applications
│   ├── web/                 Next.js 15 frontend
│   ├── core-api/             FastAPI — auth, portfolios, watchlists, alerts,
│   │                         notifications, real-time WebSocket layer, market data
│   └── ai-service/            FastAPI — hybrid ML decision engine
├── packages/                Shared, publishable-in-spirit workspace packages
│   ├── ui/                   Design system (tokens, primitives, composite components)
│   ├── config/                Shared eslint/tsconfig/tailwind config
│   └── validation/            Shared Zod schemas (form input + WebSocket payload validation)
├── libs/                    Shared Python libraries (installed editable by both backends)
│   ├── domain_common/         Value objects (Money, Ticker, typed IDs)
│   ├── auth_common/            Shared auth primitives
│   └── observability/          Structured logging setup
├── infra/                   Deployment/orchestration
│   └── docker-compose.yml     Local multi-service orchestration (profiles: core/ml/full)
├── docs/                    Documentation
│   ├── architecture/          Frozen architecture blueprint (8 numbered docs + ADRs)
│   └── phase-*/                Per-phase implementation records (the authoritative
│                                 "what's actually built" record — see below)
├── .localdev/               Local-only dev scratch environment (see note below)
├── package.json             Root workspace manifest (pnpm + turbo)
├── pnpm-workspace.yaml       pnpm workspace glob (apps/*, packages/*)
├── turbo.json                Turborepo task graph config
└── README.md                 Entry point
```

**Note on planned-but-not-yet-built paths:** the architecture blueprint
(`docs/architecture/02-clean-architecture-folder-frontend.md`) names
`packages/types/` (shared TS types generated from OpenAPI schemas) and a
top-level `ml/` directory (training pipelines/notebooks) as part of the
target structure. Neither exists yet — this is disclosed accurately in
`libs/domain_common/README.md`, which marks the one component that depends
on `ml/` (`features/registry.py`) as "Not yet implemented." There is no
`scripts/` directory in this repo; local dev bootstrap is via
`docker compose` (see `DEPLOYMENT_GUIDE.md`) and each service's own
`pyproject.toml`/`package.json` scripts.

**Note on `.localdev/`:** this is a large, machine-local scratch directory
(vendored Postgres/Redis binaries, a live Postgres data directory, manual
test-run artifacts) used during this project's Windows-native local
development (no Docker on the dev machine). It is **not** part of the
application and is unrelated to the `infra/docker-compose.yml`-based setup
documented in `DEPLOYMENT_GUIDE.md`. See `FINAL_REPOSITORY_REVIEW.md` §6
for its git-tracking status, which requires the repository owner's
decision.

---

## `apps/web` — Next.js 15 frontend

```
apps/web/
├── app/                     Next.js App Router — pages, layouts, route handlers
│   ├── (auth)/                Route group: login/register/forgot-password (shared layout)
│   ├── dashboard/              Authenticated app shell: portfolios/watchlists/alerts/
│   │                           notifications/ai pages, each with [id] dynamic routes
│   ├── layout.tsx              Root layout — metadata, providers
│   ├── page.tsx                 Landing page composition
│   ├── error.tsx                 Root error boundary
│   ├── sitemap.ts                 Generated sitemap
│   └── robots.ts                   robots.txt generator
├── features/                Feature-sliced modules — one folder per domain area
│   ├── ai/                    AI dashboard, forecast/prediction charts, SHAP explainability
│   ├── alerts/                 Alert CRUD, list, create dialog
│   ├── auth/                    Login/register/forgot-password forms, route guards
│   ├── dashboard-shell/           Shared dashboard chrome (nav, magnetic button, etc.)
│   ├── landing/                    Marketing page sections (Hero, Features, FAQ, etc.)
│   ├── market-data/                 Quotes, charts (OHLCV/price), instrument search
│   ├── notifications/                Notification list, preferences form
│   ├── portfolio/                     Portfolio summary, transaction dialog
│   ├── realtime/                       Shared WebSocket connection hook, toast, animated number
│   └── watchlist/                       Watchlist CRUD, table, symbol search
├── lib/                     Typed API clients (one per backend domain) + shared HTTP helpers
├── store/                   Zustand global state (auth store)
├── styles/                  Global CSS (Tailwind entry + CSS variables)
├── e2e/                     Playwright end-to-end tests
├── middleware.ts            Edge middleware — security headers, CSP, route gating
└── package.json
```

Every feature component under `features/*/components/` has a co-located
`.test.tsx` file (React Testing Library + Vitest). Naming: `PascalCase.tsx`
throughout — verified consistent, no exceptions.

---

## `apps/core-api` — FastAPI backend

Clean Architecture layering (see
`docs/architecture/02-clean-architecture-folder-frontend.md` §5 for the
full rationale):

```
apps/core-api/
├── src/
│   ├── domain/                Entities, value objects, domain exceptions, repository
│   │                           protocols — zero framework dependencies
│   ├── application/            Use cases — orchestrate domain + repositories,
│   │                            zero FastAPI/SQLAlchemy imports
│   ├── infrastructure/          Concrete implementations: SQLAlchemy repositories,
│   │                            Redis clients, HTTP clients, realtime streaming services
│   ├── presentation/             FastAPI routers, DTOs (Pydantic request/response models),
│   │                            dependency wiring, middleware
│   ├── config.py                  Pydantic Settings — the single source of truth for
│   │                              every environment variable this service reads
│   └── main.py                     App factory, lifespan (startup/shutdown), router registration
├── alembic/
│   └── versions/                 Sequential migrations: 0001_identity_access.py
│                                  through 0006_alerts_user_id_index.py — no gaps
├── tests/
│   ├── unit/                      Mirrors src/ structure 1:1
│   ├── integration/                 Real Postgres/Redis via testcontainers
│   └── e2e/                          Full-stack health checks
├── .env.example                   Every Settings field documented with a working default
└── pyproject.toml
```

Naming: `snake_case.py` throughout — verified consistent, no exceptions.

---

## `apps/ai-service` — FastAPI ML service

Same Clean Architecture layering as `core-api`:

```
apps/ai-service/
├── src/
│   ├── domain/                Entities (Recommendation, PredictionRun, ModelVersion),
│   │                           value objects (ModelFamily, Verdict, DataQuality)
│   ├── application/             Use cases: predict, forecast, train/retrain, sentiment,
│   │                            portfolio recommendation, model status/history
│   │   └── ml/decision_engine.py   The Hybrid Decision Engine — weighted-votes
│   │                                LSTM/ARIMA/Prophet/Random Forest/XGBoost/FinBERT
│   ├── infrastructure/
│   │   └── ml/models/               One wrapper class per model family (train/predict/
│   │                                save/load), feature engineering, SHAP explainability
│   └── presentation/               Routers (ml, health, metrics), DTOs, internal-service
│                                   auth middleware (rejects any caller lacking core-api's
│                                   shared internal token)
├── tests/
├── .env.example
└── pyproject.toml
```

`ai-service` is never directly reachable by the browser — `core-api`'s AI
proxy (`src/presentation/routers/ai_proxy_router.py` +
`src/infrastructure/http/ai_service_client.py`) is the only permitted
caller, enforced by the internal-token middleware referenced above.

---

## `packages/*` — shared workspace packages

- **`packages/ui`** — design tokens (`src/tokens/`), primitives (`src/primitives/Button`, etc.), composite components (`src/composite/Card`, etc.). Consumed by `apps/web` via `@investiq/ui`.
- **`packages/config`** — shared ESLint base config, Tailwind preset, base/Next.js `tsconfig.json`. Consumed by every other workspace package/app.
- **`packages/validation`** — Zod schemas, split by domain (`auth.ts`, `portfolio.ts`, `watchlist.ts`, `alerts.ts`, `notifications.ts`, `realtime-payloads.ts`). Consumed by `apps/web` for both form validation and runtime validation of untrusted WebSocket payloads.

## `libs/*` — shared Python libraries

Each is installed as an **editable** Poetry dependency by both `core-api`
and `ai-service` (`poetry add --editable ../../libs/<name>`), so a change
to a shared value object is immediately visible to both services without a
publish step.

- **`libs/domain_common`** — `Money` (Decimal-backed, never float), `Ticker`, typed UUID identifiers.
- **`libs/auth_common`** — shared auth primitives used identically by both services' internal-token verification.
- **`libs/observability`** — structured logging (`structlog`) configuration shared by both services' `main.py`.

## `docs/`

- **`docs/architecture/`** — the frozen architecture blueprint: 8 numbered documents (`01`–`08`), a `REVIEW-LOG.md` recording a full review pass across all 8, and `adr/` (Architecture Decision Records — the only sanctioned way to deviate from the blueprint, per the root README).
- **`docs/phase-1/` through `docs/phase-9/`** — per-phase implementation summaries, verification reports, and known-issues documents. This is the authoritative record of what has actually been built, phase by phase (the architecture blueprint's own roadmap document describes the *original plan*, which drifted somewhat from actual execution — see `FINAL_REPOSITORY_REVIEW.md` §5).
