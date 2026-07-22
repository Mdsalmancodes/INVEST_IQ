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
  ai-service/   FastAPI + Celery — predictions, sentiment, risk, optimization, SHAP
packages/
  ui/           Shared design system (design tokens, primitives, charts, motion)
  config/       Shared eslint/tsconfig/tailwind config
  types/        Shared TS types generated from OpenAPI schemas
  validation/   Shared Zod schemas
libs/           Python shared libraries (domain_common, auth_common, observability)
infra/          Docker, docker-compose, nginx
ml/             Model training pipelines, notebooks, evaluation
docs/           Architecture blueprint, ADRs
scripts/        Dev bootstrap, migration runners, staging seed scripts
```

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

Phase 1 (Foundation & Skeleton) — in progress. See `docs/architecture/08-coding-standards-git-roadmap.md` §24 for the full Phase 1–10 roadmap.
