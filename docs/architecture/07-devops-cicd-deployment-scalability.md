# INVEST IQ — Architecture Blueprint
## Document 7 of N: DevOps, CI/CD, Docker, Deployment, Scalability, Performance Optimization

> Status: DRAFT — pending founder approval

---

## 17. DevOps & Environment Strategy

### 17.1 Environments

| Environment | Purpose | Infra |
|---|---|---|
| Local | Individual developer machine | Docker Compose, all services + DBs containerized |
| CI | Automated test execution | Ephemeral containers spun up per pipeline run (GitHub Actions services / testcontainers) |
| Staging | Pre-production validation, QA, demo | Single-node Docker Compose or small managed container service (cost-conscious at this stage — full K8s is premature) |
| Production | Live platform | Managed container orchestration (see §19), designed to migrate to K8s without rearchitecture when scale justifies it |

### 17.2 Environment Configuration

All configuration via environment variables, loaded through a centralized, validated config module per service — **no scattered `os.environ.get()` calls throughout the codebase.**

```python
# apps/core-api/src/config.py
class Settings(BaseSettings):
    database_url: PostgresDsn
    redis_url: RedisDsn
    jwt_secret: SecretStr
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = []

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()  # fails fast at startup if required vars are missing/invalid
```

```typescript
// apps/web/lib/env.ts — validated at build/runtime via Zod, same principle
const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url(),
  NEXTAUTH_SECRET: z.string().min(32),
  DATABASE_URL: z.string().url().optional(), // only if web owns any direct DB access (rare, BFF-only ideally)
});
export const env = envSchema.parse(process.env); // fails fast at build
```

**Fail-fast principle:** a missing/invalid required environment variable crashes the service at startup with a clear error, never at first-request-that-happens-to-need-it. This surfaces misconfiguration in deployment pipelines immediately, not as an intermittent production incident hours later.

### 17.3 Docker Strategy

**Multi-stage builds, every service, no exceptions** — minimizes final image size and attack surface (build tools/dev dependencies never ship in the runtime image).

```dockerfile
# apps/core-api/Dockerfile (representative pattern for all Python services)
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd --create-home --shell /bin/bash appuser   # never run as root
WORKDIR /app
COPY --from=builder /deps /usr/local/lib/python3.12/site-packages
COPY src/ ./src/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# apps/web/Dockerfile (Next.js — standalone output mode for minimal runtime image)
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build   # next.config.ts has output: 'standalone'

FROM node:20-alpine AS runtime
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
USER appuser
EXPOSE 3000
CMD ["node", "server.js"]
```

**Non-negotiable image hardening rules:**
- Never run as root (`USER appuser` in every image).
- Pin base image versions exactly (`python:3.12-slim`, not `python:latest`).
- No secrets baked into image layers (all via runtime env injection).
- `HEALTHCHECK` defined in every image, matching the `/health` contract (Document 5 §14.4).
- Base images scanned for CVEs in CI (Trivy or Docker Scout) — build fails on High/Critical.

### 17.4 Docker Compose (Local Dev Orchestration)

> **REVISION (post-architecture-review):** the original Compose file ran 10 containers (3 DBs + 4 backend services + Celery worker + web + nginx) unconditionally for any single feature — flagged as an unjustified local-dev burden, especially given Document 3 §7.1's service collapse to 2 backend deployables. **Fix: Compose `profiles`** so a developer only starts what their current work actually touches, plus a mock ai-service client so core-api work never hard-depends on the ML stack being up locally.

```yaml
# infra/docker-compose.yml (representative structure, not exhaustive)
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: investiq
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: {test: ["CMD-SHELL", "pg_isready -U postgres"], interval: 5s}
    profiles: ["core", "ml", "full"]

  redis-cache:
    image: redis:7-alpine
    command: redis-server --maxmemory-policy allkeys-lru
    profiles: ["core", "ml", "full"]

  redis-broker:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redisbrokerdata:/data]
    profiles: ["core", "ml", "full"]

  redis-session:
    image: redis:7-alpine
    volumes: [redissessiondata:/data]
    profiles: ["core", "ml", "full"]

  mongo:
    image: mongo:7
    volumes: [mongodata:/data/db]
    profiles: ["ml", "full"]     # only needed for ai-service / feature-store work

  core-api:
    build: {context: ../apps/core-api}
    depends_on:
      postgres: {condition: service_healthy}
      redis-cache: {condition: service_started}
      redis-broker: {condition: service_started}
      redis-session: {condition: service_started}
    env_file: ../apps/core-api/.env
    environment:
      # When the "ml" profile isn't active, core-api talks to its own
      # MockAiServiceClient (Document 3 §7.1) instead of a real ai-service —
      # set via env flag, not a code branch, so behavior is explicit and testable.
      AI_SERVICE_MODE: ${AI_SERVICE_MODE:-mock}
    ports: ["8001:8000"]
    profiles: ["core", "ml", "full"]

  ai-service:
    build: {context: ../apps/ai-service}
    depends_on: [redis-cache, redis-broker, mongo]
    ports: ["8002:8000"]
    profiles: ["ml", "full"]

  ai-service-worker:
    build: {context: ../apps/ai-service}
    command: celery -A src.worker worker -Q ml-inference,ml-training -l info
    depends_on: [redis-broker, mongo]
    profiles: ["ml", "full"]

  web:
    build: {context: ../apps/web}
    depends_on: [core-api]
    ports: ["3000:3000"]
    profiles: ["core", "ml", "full"]

  nginx:
    build: {context: ./nginx}
    depends_on: [web, core-api]
    ports: ["80:80"]
    profiles: ["core", "ml", "full"]

volumes: {pgdata: {}, mongodata: {}, redisbrokerdata: {}, redissessiondata: {}}
```

**Usage**: `docker compose --profile core up` (Postgres + 3 Redis instances + `core-api` + `web` — 6 containers, sufficient for portfolio/watchlist/alerts/screener/market-data feature work using the mock ML client). `docker compose --profile ml up` adds Mongo + `ai-service` + its Celery worker for ML pipeline work. `docker compose --profile full up` runs everything, used before opening a PR that touches both sides of the BFF↔service contract (§18.2's contract test job mirrors this locally too).

Local dev additionally supports a `docker-compose.override.yml` for hot-reload mounts (bind-mounting source directories + running dev servers instead of production builds) — production Dockerfiles are never used unmodified for local dev iteration speed.

---

## 18. CI/CD (GitHub Actions)

### 18.1 Pipeline Structure

```
.github/workflows/
├── ci.yml              # Runs on every PR: lint, typecheck, unit+integration tests, build,
│                          smoke-tier E2E (Document 6 §16.6 revision)
├── contract-check.yml   # NEW — regenerates packages/types from live service OpenAPI
│                          schemas, runs tsc --noEmit against web (Document 6 §16.2 revision)
├── security-scan.yml   # Dependency + container vulnerability scanning
├── e2e.yml              # Runs on merge to main: full E2E against preview env
├── resilience.yml        # NEW — chaos/resilience suite (Document 6 §16.2a), main branch only
├── deploy-staging.yml   # Auto-deploy on merge to `develop`
└── deploy-production.yml # Manual-approval-gated deploy on merge to `main`
```

### 18.2 CI Pipeline (representative)

```yaml
# .github/workflows/ci.yml
name: CI
on: [pull_request]
jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup pnpm + Python
        run: |
          corepack enable
          pip install poetry
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: cd apps/core-api && poetry install && poetry run ruff check . && poetry run mypy --strict src/

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm test:unit --coverage
      - run: cd apps/core-api && poetry run pytest tests/unit --cov=src --cov-fail-under=80

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres: {image: postgres:16-alpine, env: {POSTGRES_PASSWORD: test}}
      redis: {image: redis:7-alpine}
    steps:
      - uses: actions/checkout@v4
      - run: cd apps/core-api && poetry run pytest tests/integration

  build:
    needs: [lint-and-typecheck, unit-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f apps/core-api/Dockerfile apps/core-api
      - run: docker build -f apps/web/Dockerfile apps/web
      # ...remaining services

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aquasecurity/trivy-action@0.24.0
        with: {scan-type: 'fs', severity: 'CRITICAL,HIGH', exit-code: '1'}
```

### 18.3 Deployment Pipeline

```
merge to `develop` ──▶ deploy-staging.yml ──▶ build images ──▶ push to registry
                                          ──▶ deploy to staging environment
                                          ──▶ run smoke tests against staging
                                          ──▶ (on success) notify team channel

merge to `main` ──▶ deploy-production.yml ──▶ build images (or promote staging
                                                image if identical commit — image
                                                promotion preferred over rebuild to
                                                guarantee staging-tested artifact
                                                is exactly what ships)
                                          ──▶ REQUIRES manual approval gate
                                          ──▶ database migrations run FIRST,
                                              backward-compatible only (see §18.4)
                                          ──▶ rolling deploy (old + new versions
                                              briefly coexist — this is why
                                              migrations must be backward-compatible)
                                          ──▶ health check verification before
                                              old version is fully decommissioned
                                          ──▶ automatic rollback on health check
                                              failure
```

### 18.4 Database Migration Discipline

**Every migration must be backward-compatible with the previous application version** during the rolling-deploy window:

```
Safe: adding a nullable column, adding a new table, adding an index (concurrently)
Unsafe (without a multi-step process): dropping a column, renaming a column,
       changing a column type, adding a NOT NULL constraint to an existing column

Multi-step pattern for a "risky" change (e.g., renaming a column):
  Deploy N:   add new column, dual-write to both old and new in application code
  Deploy N+1: backfill old data into new column, read from new column
  Deploy N+2: stop writing to old column
  Deploy N+3: drop old column
```

This discipline is stated explicitly because skipping it is the single most common cause of production incidents during deploys in real systems — a naive single-step "rename column" migration deployed alongside new code will break every in-flight request served by the previous version's still-running instance during a rolling deploy.

Migrations run via Alembic (Python services) with a CI check that fails the build if a migration is detected as "unsafe" without an explicit override comment acknowledging the multi-step plan is in progress.

---

## 19. Deployment Architecture

### 19.1 Launch-Stage Topology (cost-conscious, not over-provisioned)

```
                          ┌─────────────────┐
                          │   CDN / Edge      │  (Cloudflare or equivalent)
                          │   (static assets,  │
                          │   DDoS protection) │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Load Balancer      │
                          └────────┬─────────┘
                                   │
              ┌─────────────────┼─────────────────┐
              ▼                                     ▼
   ┌───────────────────┐                  ┌───────────────────┐
   │  Container host 1    │                  │  Container host 2    │
   │  (web, core-api,      │                  │  (web, core-api,      │
   │   ai-service, etc.)   │                  │   ai-service, etc.)   │
   └───────────────────┘                  └───────────────────┘
              │                                     │
              └─────────────────┬─────────────────┘
                                 ▼
              ┌──────────────────────────────────────┐
              │  Managed Postgres (PITR enabled) |      │
              │  Managed Redis ×3 (cache/broker/session,│
              │  broker+session with Multi-AZ failover) |│
              │  Managed Mongo (automated snapshots)     │
              │  — full backup/DR detail: Doc 3 §8.5      │
              └──────────────────────────────────────┘
```

Recommended launch-stage platform choices (managed, not self-operated Kubernetes, to minimize DevOps burden pre-scale): AWS ECS Fargate / Google Cloud Run / Railway / Render — any of these run the same Docker images built in §17.3 without modification, which is precisely why the containerized, config-via-env approach matters: **the application is deployment-target-agnostic.**

**Ephemeral preview environments (gap identified in review — noted as an accepted tradeoff, not silently absent):** at launch scale, all feature branches share one Staging environment (§17.1) rather than each getting a per-PR ephemeral environment — this is a deliberate cost/complexity tradeoff for a small team, not an oversight. Revisit once the team consistently runs more than ~4 concurrent feature branches, at which point per-PR preview environments (most managed platforms above support this natively) become worth the added CI cost.

### 19.2 Path to Kubernetes (Phase 9+, not built now, but not blocked either)

Because every service is already: containerized, stateless (session state in Redis not memory), configured via env vars, health-check compliant — migrating to K8s later is an infrastructure-team exercise (writing Deployment/Service/HPA manifests) rather than an application rewrite. `infra/k8s/` is scaffolded with placeholder manifests now precisely to keep this path visible in the architecture without committing engineering time to it prematurely.

### 19.3 Scalability Design Points (stated per-component)

| Component | Bottleneck if unaddressed | Scaling approach |
|---|---|---|
| `core-api` (HTTP request path) | Request throughput | Horizontal (stateless, add replicas behind LB) |
| `core-api` (market-data ingestion workers) | Vendor rate limits, not compute | Careful request scheduling/pooling, NOT just adding replicas (would multiply vendor rate-limit consumption, not help) — scales as a distinct worker-process-group within the `core-api` deployment (Document 3 §7.1), independent of the HTTP replica count |
| `core-api` (WS/notification module) | WS connection count per instance | Horizontal, connection count monitored (per-user and per-IP caps, Document 3 §7.6), Redis Pub/Sub means any instance can serve any subscription |
| `ai-service` (inference) | CPU-bound model inference | Horizontal, separate pool from training workers |
| `ai-service` (training workers) | CPU/memory-heavy batch jobs | Vertical (bigger machines) + scheduled off-peak execution |
| Postgres | Write throughput, connection count | Read replicas for read-heavy queries (portfolio history, screener), connection pooling (PgBouncer), read-after-write consistency rule (Document 3 §7.7) keeps replica lag invisible to users, vertical scaling before sharding is ever needed; `ohlcv_bars` partitioned from day one (Document 3 §8.4 revision) |
| Redis | Memory for quote cache across thousands of symbols; conflicting durability needs across workloads | REVISION (gap identified in review — single instance was a documented SPOF): split into 3 instances by workload (Document 3 §7.7) — `redis-cache` (no persistence, LRU-evicted, horizontally shardable via Redis Cluster if truly needed later), `redis-broker` and `redis-session` (managed with Multi-AZ automatic failover, since these are NOT acceptable single points of failure at any scale) |
| Mongo | News/feature document volume | Sharding by symbol or time-range if volume justifies it — not needed at launch scale |

### 19.3a Feature Flags & Gradual Rollout (missing entirely from the original draft — added per architecture review)

No mechanism existed anywhere in the original blueprint for shipping a risky change (a new ML model version, a new UI feature) to a subset of users before full rollout — Document 4 §10.8's model promotion was an instant 100%-cutover, and `FeatureEntitlement` (Document 1 §1.4) is a billing/tier gate, not a rollout mechanism; the two were conflated by omission. Fixed:

- **General-purpose feature flag service**: a lightweight flag evaluation module within `core-api` (backed by `redis-session`, flag definitions in Postgres for auditability), supporting boolean flags and percentage/cohort rollouts, hashed deterministically on `user_id` so a given user's experience is stable across requests rather than flickering between variants.
- **Model rollout reuses this mechanism**: Document 4 §10.8's canary `rollout_percentage` on `ModelVersion` is implemented as a specific application of this same general flag infrastructure, not a bespoke parallel system — the recommendation-weight A/B testing mentioned in Document 4 §10.4 ("weights tuned/A-B tested without a code deploy") is the flag service's first concrete production use case, closing a gap where that claim previously had no supporting infrastructure described anywhere.
- **Kill switch usage**: any newly shipped feature-flagged capability can be disabled instantly platform-wide (flag flipped to 0%) without a deploy — this is the operational safety net for Phase 6+ features before they've earned full confidence.

### 19.4 Performance Optimization (Full-Stack Checklist)

**Frontend:**
- Code splitting per route (automatic via Next.js App Router) + explicit dynamic imports for heavy components (R3F scenes, charting libraries, PDF export if added later).
- Image optimization via `next/image` (automatic AVIF/WebP, responsive sizing, lazy loading below the fold).
- Font optimization via `next/font` (self-hosted, no render-blocking external font requests).
- Virtualized lists/tables beyond 50 rows (Document 2 §6.4).
- React Query `staleTime`/`gcTime` tuned per data type (quotes: near-zero staleTime; fundamentals: hours).
- Bundle analysis in CI (`@next/bundle-analyzer`) with a size-budget check to catch regressions.
- Lighthouse CI gate (Document 6 §16.3).

**Backend:**
- Database query optimization: every list endpoint reviewed for N+1 queries (SQLAlchemy `selectinload`/`joinedload` used deliberately, not accidentally lazy-loaded in a loop).
- Connection pooling (SQLAlchemy async engine pool sized appropriately per service replica count).
- Response compression (gzip/brotli at the reverse proxy layer).
- Async I/O throughout (FastAPI async endpoints, async DB drivers — `asyncpg`, Motor for Mongo) so a single process handles many concurrent I/O-bound requests without blocking.

**ML/AI:**
- Model inference batching where possible (scoring multiple symbols' sentiment in one FinBERT batch call rather than one-by-one).
- Feature store pre-computation on a schedule (Document 4 §10.2) so real-time prediction requests read pre-computed features rather than recomputing indicators from raw bars on every request.
- Model artifact loaded once at worker startup (not per-request), kept warm in memory.

---

*End of Document 7. Continuing in Document 8: Design System detail, Coding Standards, Git Workflow, Naming Conventions, Documentation Standards, and the Development Roadmap (Phase 1–10).*
