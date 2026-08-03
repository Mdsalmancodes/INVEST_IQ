# INVEST IQ

AI-powered investment intelligence platform. Educational/informational tooling — **not a licensed broker-dealer and not financial advice** (see `docs/architecture/01-product-and-system-architecture.md` §1.1).

## Architecture

The architecture is **frozen** as of founder approval on 2026-07-21. Full blueprint: [`docs/architecture/`](./docs/architecture/) (documents 01–08 + `REVIEW-LOG.md`). Any deviation from the blueprint during implementation requires an ADR in [`docs/architecture/adr/`](./docs/architecture/adr/) — see that directory's `README.md` for the process. Do not silently modify the documented design.

## Monorepo Structure

```
apps/
  web/          Next.js 15 frontend
  core-api/     FastAPI — auth, users, portfolio, watchlist, screener, alerts,
                notifications (WS), market data ingestion
  ai-service/   FastAPI — hybrid ML decision engine (LSTM/ARIMA/Prophet/
                Random Forest/XGBoost/FinBERT), portfolio recommendations
packages/
  ui/           Shared design system (design tokens, primitives, charts, motion)
  config/       Shared eslint/tsconfig/tailwind config
  validation/   Shared Zod schemas
libs/           Python shared libraries (domain_common, auth_common, observability)
infra/          Docker, docker-compose
docs/           Architecture blueprint, ADRs, per-phase implementation records
```

`packages/types/` and a top-level `ml/` training-pipeline directory are named in the
architecture blueprint (`docs/architecture/02-clean-architecture-folder-frontend.md`)
but not yet built as of this writing — see that document and
`libs/domain_common/README.md` for their planned scope. There is no top-level
`scripts/` directory; local dev bootstrap is via `docker compose` (below) and each
service's own `pyproject.toml`/`package.json` scripts.

See `docs/architecture/02-clean-architecture-folder-frontend.md` §5 for the full rationale and per-service internal structure.

## Local Development

Requires Docker, Docker Compose, Node.js ≥20, pnpm, Python ≥3.12, Poetry.

```bash
# Copy env templates and fill in real values
cp apps/core-api/.env.example apps/core-api/.env
cp apps/ai-service/.env.example apps/ai-service/.env
cp apps/web/.env.example apps/web/.env

# Start just the core stack (Postgres, 3 Redis instances, core-api, web) —
# sufficient for portfolio/watchlist/alerts/screener/market-data work.
# ai-service calls are served by core-api's MockAiServiceClient in this profile.
docker compose -f infra/docker-compose.yml --profile core up

# Add the ML stack (Mongo, ai-service, its Celery workers) when needed
docker compose -f infra/docker-compose.yml --profile ml up

# Full stack (equivalent to core + ml)
docker compose -f infra/docker-compose.yml --profile full up
```

Health checks: `GET /health` (liveness) and `GET /ready` (readiness) on every backend service, per `docs/architecture/05-data-pipeline-notifications-caching-monitoring.md` §14.4.

## Status

Core functionality across auth, portfolios, watchlists, alerts, notifications,
real-time market data (WebSocket), and the AI/ML decision engine (predictions,
sentiment, portfolio recommendations) is implemented and covered by an
automated test suite. See `docs/phase-*/` for the per-phase implementation
records and `docs/architecture/08-coding-standards-git-roadmap.md` §24 for the
original phase roadmap (phase names/scope evolved during implementation —
the per-phase docs under `docs/phase-*/` reflect what was actually built,
which is the authoritative record of current status).
