# Deployment Guide

This guide covers running INVEST_IQ locally via Docker Compose (the
documented, portable path) and the production-shaped multi-stage Docker
images each service already builds. It does not prescribe a specific cloud
target (AWS/GCP/Azure/etc.) — see `docs/architecture/07-devops-cicd-deployment-scalability.md`
for the full deployment/scalability architecture and rationale.

## Prerequisites

- Docker + Docker Compose
- Node.js ≥20, pnpm (`packageManager: pnpm@9.12.0` pinned in root `package.json`)
- Python ≥3.12, Poetry (only needed for running services outside Docker)

## 1. Environment configuration

Every service ships a `.env.example` documenting exactly the environment
variables its own config-loading code reads — nothing more, nothing less
(verified during the repository review; see `FINAL_REPOSITORY_REVIEW.md`).

```bash
cp apps/core-api/.env.example apps/core-api/.env
cp apps/ai-service/.env.example apps/ai-service/.env
cp apps/web/.env.example apps/web/.env
```

Then edit each `.env` and replace every `change-me-...` placeholder with a
real value. At minimum, for anything beyond local dev:

- `apps/core-api/.env`: `JWT_SECRET` (≥32 chars, enforced by `Settings`'s own validator), `INTERNAL_SERVICE_TOKEN` (must match `apps/ai-service/.env`'s value exactly — this is the shared secret that lets `ai-service` verify a request actually came from `core-api`)
- `apps/ai-service/.env`: `INTERNAL_SERVICE_TOKEN` (same value as above)

**Never commit a real `.env` file.** `.gitignore` already excludes `.env`,
`.env.local`, and `.env.*.local` while explicitly allowing `.env.example`
files through (`!.env.example`).

## 2. Local development via Docker Compose

`infra/docker-compose.yml` defines three profiles so you only start what
your current work touches:

```bash
# Core stack: Postgres, 3 Redis instances, core-api, web.
# ai-service calls are served by core-api's MockAiServiceClient in this profile
# (AI_SERVICE_MODE defaults to "mock" unless overridden).
docker compose -f infra/docker-compose.yml --profile core up

# Adds Mongo + ai-service on top of the core stack
docker compose -f infra/docker-compose.yml --profile ml up

# Everything (equivalent to core + ml)
docker compose -f infra/docker-compose.yml --profile full up
```

**Build context note:** every service's Dockerfile must be built with the
**monorepo root** as build context (not the service subdirectory), because
`core-api`/`ai-service` depend on the editable local package
`libs/observability`, and `web` depends on the pnpm workspace's
`packages/ui`/`packages/config`. `docker-compose.yml` already sets
`context: ..` correctly for each service — if building manually, replicate
this:

```bash
docker build -f apps/core-api/Dockerfile .
docker build -f apps/ai-service/Dockerfile .
docker build -f apps/web/Dockerfile .
```

### Ports (local Docker Compose)

| Service | Container port | Host port |
|---|---|---|
| web | 3000 | 3000 |
| core-api | 8000 | **8001** |
| ai-service | 8000 | **8002** |
| postgres | 5432 | 5432 |
| redis-cache | 6379 | 6379 |
| redis-broker | 6379 | **6380** |
| redis-session | 6379 | **6381** |
| mongo (ml/full profiles only) | 27017 | 27017 |

## 3. Database migrations

Migrations are **not** run automatically by the Dockerfile or
`docker-compose.yml` — run them explicitly after Postgres is up and before
serving traffic:

```bash
cd apps/core-api
poetry install
poetry run alembic upgrade head
```

To verify the current migration state without applying anything:

```bash
poetry run alembic current
```

Migrations are sequential and numbered (`0001_identity_access.py` through
`0006_alerts_user_id_index.py` as of this writing) — always run `upgrade
head`, never target a specific revision unless you have a specific reason
to.

## 4. Health checks

Every backend service (`core-api`, `ai-service`) exposes:

- `GET /health` — liveness (process is up)
- `GET /ready` — readiness (dependencies like Postgres/Redis are reachable)

per `docs/architecture/05-data-pipeline-notifications-caching-monitoring.md`
§14.4. `docker-compose.yml`'s own service healthchecks (Postgres/Redis/Mongo)
gate `depends_on: condition: service_healthy` for `core-api`, so it will not
start against a database that isn't actually ready yet.

## 5. Running without Docker (native, e.g. Windows without WSL)

Each backend service can run directly via Poetry, and the frontend via pnpm,
provided you have real Postgres/Redis instances reachable at the URLs in
your `.env` files:

```bash
# core-api
cd apps/core-api
poetry install
poetry run alembic upgrade head
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8001

# ai-service
cd apps/ai-service
poetry install
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8002

# web
cd apps/web
pnpm install
pnpm dev
```

`AI_SERVICE_MODE=live` in `apps/core-api/.env` is required for the frontend's
AI features to hit the real `ai-service` process rather than
`MockAiServiceClient`.

## 6. Production image build

Each service's `Dockerfile` is a multi-stage build (builder stage compiles/
installs dependencies; runtime stage is a minimal, non-root image):

- **`apps/web/Dockerfile`**: `node:20-alpine`, three stages (deps → builder → runtime), Next.js standalone output, runs as a non-root `appuser`.
- **`apps/core-api/Dockerfile`** / **`apps/ai-service/Dockerfile`**: `python:3.12-slim`, two stages (builder exports Poetry's lockfile to `requirements.txt` and installs into `/deps`; runtime copies only `/deps` + `src/`), runs as a non-root `appuser`, has a `HEALTHCHECK` instruction hitting `/health`.

None of the three Dockerfiles bake in a real `.env` — production secrets
must be supplied at deploy time via your platform's secret-management
mechanism (environment variables, mounted secrets, etc.), not committed to
the image.

## 7. Security-sensitive configuration checklist before any real deployment

- [ ] `JWT_SECRET` is a real, randomly generated value ≥32 characters (not the placeholder)
- [ ] `INTERNAL_SERVICE_TOKEN` is a real, randomly generated value, identical in both `core-api` and `ai-service`'s environment
- [ ] `CORS_ALLOWED_ORIGINS` is set to your real frontend origin(s) only — the default fails closed (empty list) if unset, so an unconfigured deployment will reject all cross-origin requests rather than silently allow everything
- [ ] `ai-service` is deployed on a network that is **not** directly reachable from the public internet or the browser — `core-api`'s AI proxy is the only intended caller, enforced by the shared internal token, but network-level isolation is still the stronger guarantee
- [ ] Rate limiting values (`RATE_LIMIT_*`) reviewed against your expected real traffic volume, not left at local-dev defaults
- [ ] No `.env` file (with real secret values) is committed to the repository — confirmed via `.gitignore`'s existing `.env` rule, but worth a final manual check before any deploy

