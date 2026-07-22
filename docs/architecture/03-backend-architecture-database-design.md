# INVEST IQ — Architecture Blueprint
## Document 3 of N: Backend Architecture, Database Design

> Status: DRAFT — pending founder approval

---

## 7. Backend Architecture (Detailed)

> **REVISION (post-architecture-review):** The original draft of this document specified 4 independently deployed Python services (`core-api`, `market-data-service`, `ai-service`, `notification-service`). An architecture review (see `docs/architecture/REVIEW-LOG.md`) found this contradicts Document 1 §2.1's own stated rationale for a modular monolith — `market-data-service` and `notification-service` do not have scaling/resource profiles distinct enough from `core-api` to justify separate deployables at pre-launch scale, and the 4-way split materially increases local-dev burden (10+ containers for any single feature) and operational surface (4x CI pipelines, 4x service-to-service auth surfaces) with no corresponding benefit yet. **Decision: collapse to 2 deployable backend services.** The bounded-context/Clean-Architecture module boundaries (Document 2 §4.1, Document 3 §3 in Doc 1) are unchanged — this is a deployment-topology simplification, not a domain redesign. Extraction back into separate services later remains mechanical (per Doc 1 §2.1's own reasoning) because each module still only talks to others through its repository/service interfaces, never direct cross-module DB access.

### 7.1 Service Boundaries and Responsibilities

| Service | Contains modules | Sync/Async | Scaling profile |
|---|---|---|---|
| `core-api` | Auth, Users, Portfolio, Watchlist, Screener, Alerts, Notifications (REST + WS), Market Data ingestion & serving, Admin | Mixed (sync REST for CRUD; async Celery workers in-process-group for ingestion/alerts; WS endpoint for real-time) | Horizontal, stateless, scale on request volume + WS connection count |
| `ai-service` | Prediction inference, sentiment scoring, risk calc, optimization, SHAP explainability, model training | Async-heavy (Celery tasks for training/backtesting; sync FastAPI for real-time inference calls) | Scale on CPU (inference) separately from GPU (training, if used) — genuinely distinct resource profile from `core-api`, which is why this is the one service kept independently deployable from day one |

`core-api` is internally still organized as separate modules with separate Celery queues (`market-data`, `alerts`, `notifications` — Document 3 §7.8's queue isolation already achieves the "don't let a slow job starve alert delivery" property without needing separate deployables). Each module's Celery workers run as a **separate deployment/process group** from the API process itself (so ingestion polling or alert sweeps never compete with request-serving for CPU), but they still ship from the same codebase/image family and are versioned/deployed together — this is what "modular monolith" means concretely here.

`core-api` exposes a **narrow internal REST API** to `ai-service`, and both are consumed by the Next.js BFF layer — never directly by the browser (except the WebSocket endpoint on `core-api`'s notification module, which the browser connects to directly after receiving a signed connection token).

**Local development impact (fixes the "10-container" problem):** Document 7 §17.4's Docker Compose is updated to use Compose `profiles` — a developer working on a `core-api` module (portfolio, watchlist, alerts, market data) runs `docker compose --profile core up` (Postgres, Redis, `core-api` only — 3 containers). `ai-service` work adds `--profile ml` (adds Mongo, `ai-service`, its Celery workers). Full-stack verification before a PR uses `--profile full`. `core-api` additionally ships a `MockAiServiceClient` (implementing the same `AiServiceClient` interface used in production) that returns realistic fixture-based forecasts/sentiment/risk data when `ai-service` is not running locally, so frontend and core-api feature work never hard-depend on the ML stack being up.

### 7.2 Inter-Service Communication

- **Synchronous**: internal REST over HTTPS, service-to-service JWT (short-lived, service-identity token, distinct from user session tokens) for authn between services.
- **Asynchronous**: Redis Pub/Sub for low-latency fan-out (quote updates), Celery + Redis broker for task queues (forecast generation, sentiment batch scoring, report generation).
- **Event contracts** are versioned JSON schemas stored in `packages/types` (generated) and `libs/domain_common` — a breaking change to an event payload requires a version bump (`QuoteUpdatedV2`), old consumers keep working against `V1` until migrated. No implicit breaking changes.

```
Example event: QuoteUpdated (v1)
{
  "event": "QuoteUpdated",
  "version": 1,
  "symbol": "AAPL",
  "price": "231.42",        // string-encoded decimal, never float
  "timestamp": "2026-07-21T13:05:00Z",
  "source": "polygon",
  "sequence": 918273
}
```

### 7.3 API Gateway / BFF Pattern

Next.js Route Handlers (`app/api/**/route.ts`) act as the Backend-for-Frontend:

- Attach/verify the user's session (NextAuth or custom JWT session cookie — httpOnly, secure, sameSite=strict).
- Translate browser requests into internal service calls, injecting the service-identity JWT.
- Enforce the **response envelope contract** (Section 8 in the API Design doc) uniformly, so even if an internal service forgets a field, the BFF can normalize it before the client ever sees it — though the internal services are still required to produce it correctly; the BFF is a safety net, not a crutch.
- Apply per-user rate limiting (via Redis token bucket) before proxying to internal services, protecting internal services from needing to know about end-user identity rate limits at all — they only worry about service-to-service limits.

### 7.4 Authentication Flow (detailed)

```
1. User submits credentials (or OAuth redirect completes)
        │
        ▼
2. core-api validates credentials (bcrypt compare) OR validates OAuth token
   with provider (Google/GitHub)
        │
        ▼
3. core-api issues:
   - Access Token (JWT, 15 min expiry, contains userId, roles, tokenVersion)
   - Refresh Token (opaque random string, stored hashed in Postgres +
     Redis with matching TTL, 30 day expiry, rotation on each use)
        │
        ▼
4. Next.js BFF sets Refresh Token as httpOnly+secure+sameSite=strict cookie.
   Access Token is kept in-memory on the client (NOT localStorage — mitigates
   XSS token theft) and attached as Authorization: Bearer header by the
   typed API client.
        │
        ▼
5. On Access Token expiry, client calls /auth/refresh silently, BFF forwards
   the httpOnly refresh cookie to core-api, which validates it against the
   stored hash, rotates it (issues new refresh token, invalidates old one —
   refresh token rotation prevents replay), and returns new Access Token.
        │
        ▼
6. Logout: refresh token is deleted from Postgres+Redis, cookie cleared.
   "Logout everywhere": tokenVersion on User is incremented, invalidating
   all outstanding access tokens instantly (checked on every request).
```

**Why this design:** access tokens in memory (not localStorage) removes the most common XSS-to-account-takeover vector. Refresh token rotation + hashed storage means a stolen refresh token is detected on next legitimate use (reuse detection → force logout everywhere + security alert). This is the same pattern used by Auth0/Clerk-grade systems.

### 7.5 Authorization / RBAC

**Role model:**

| Role | Scope |
|---|---|
| `user` | Own resources only (own portfolios, watchlists) |
| `pro_user` | Same as `user` + gated features (real-time data, unlimited AI assistant) — enforced via `FeatureEntitlement` check, not a separate role branch in code |
| `admin` | Platform-wide read + moderation (view any user's aggregate stats, manage news sources, manage model versions) |
| `super_admin` | Admin + user role management, billing overrides |

**Enforcement pattern (backend):** FastAPI dependency-injected guards, composable:

```python
@router.get("/portfolios/{portfolio_id}")
async def get_portfolio(
    portfolio_id: UUID,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_ownership_or_role(resource="portfolio", roles=["admin"])),
):
    ...
```

Ownership checks are **resource-level**, not just role-level — a `user` role can only ever access `Portfolio` rows where `portfolio.user_id == current_user.id`, enforced at the repository query layer (never trust a role check alone for row-level access; always scope the query).

**Frontend enforcement:** mirrors backend via a `usePermission()` hook + route-level `middleware.ts` guards, but this is UX convenience only — the backend is the actual authority. Every permission check is duplicated server-side; the frontend check never substitutes for it.

### 7.6 WebSocket Architecture

```
Client ──(1. HTTPS GET /realtime/token)──▶ core-api
       ◀──(2. short-lived WS connect token, 60s expiry)──

Client ──(3. WSS connect ws://core-api/ws?token=...)──▶ core-api (notification module)
       ◀──(4. validates token, upgrades connection, subscribes to
              Redis channels based on user's active watchlist/portfolio symbols)──

core-api (market data module) ──(publishes to Redis "quotes:{symbol}")──▶ Redis
                                                                   │
core-api (notification module, subscriber) ◀───────────────────────┘
       │
       └──(pushes frame to all WS connections subscribed to that symbol)──▶ Clients
```

- Connection tokens are separate from access tokens (short-lived, single-purpose) so a leaked WS URL doesn't leak a reusable API credential.
- The notification module maintains an in-memory map of `symbol → set[connection_id]` per instance. Horizontal scaling works because the fan-out source of truth is Redis Pub/Sub, not instance memory — any instance can serve any client regardless of which instance holds the Redis subscription.
- **Pub/Sub vs. Streams, used deliberately for different guarantees:** live quote fan-out uses plain Redis Pub/Sub (fire-and-forget) because a missed intermediate tick is harmless — it's immediately superseded by the next one. Alerts use Redis Streams with a consumer group ("notification-workers") instead, because alert delivery must be at-least-once: if a worker crashes mid-processing, another consumer in the group claims the pending entry (via `XCLAIM` after an idle timeout) rather than silently dropping a triggered alert.
- **Backpressure**: if a client's WS send buffer exceeds a threshold (slow consumer), the server drops intermediate quote ticks and sends only the latest (coalescing), never queues unboundedly.
- **Reconnection on server-side deploy/restart (gap identified in architecture review — now specified):** rolling deploys terminate WS connections when an old instance is drained. The server sends a `{"type":"reconnect_advised","retryAfterMs":<jittered value>}` frame before closing a connection during a graceful shutdown (SIGTERM handler drains: stop accepting new subscriptions, notify existing connections, wait up to N seconds, then close). The client's WS wrapper (`apps/web/lib/websocket-client.ts`, Document 2 §5.2) implements exponential backoff with jitter (base 500ms, cap 30s) and automatically re-requests a fresh connect token (step 1 above) and re-subscribes to the same symbol set it held before disconnecting — subscription state lives client-side (React Query cache of "active watchlist/portfolio symbols") so resubscription is a deterministic replay, not something the server needs to remember across the reconnect gap.
- **Connection limits:** capped both per-IP (defense against a single client opening excessive sockets) and per-user (a hard ceiling on concurrent authenticated connections, e.g. 5, covering multiple tabs/devices) — both enforced at connection-accept time by checking a Redis counter keyed by IP and by user ID respectively.

### 7.7 Caching Strategy

> **REVISION (post-architecture-review):** The original single-paragraph caching table contained an internal contradiction — OHLCV bars were described as both "hot: last 90 days" (implying eviction) and "cached forever... indefinitely" (implying no eviction) in different parts of this document. Corrected below. Additionally, this section previously assumed a single Redis instance handling quote cache, Pub/Sub, Celery broker, rate limiting, and sessions simultaneously — a review flagged this as a scalability/reliability single point of failure with conflicting persistence needs (Pub/Sub and quote cache want low-latency/no-persistence; Celery broker and sessions want durability). **Decision: split Redis into 3 logically separate instances (or managed-Redis "databases"/clusters), by workload.**

**Redis topology (revised):**

| Instance | Workloads | Persistence config | Rationale |
|---|---|---|---|
| `redis-cache` | Latest quote cache, hot OHLCV bars, screener/prediction result cache | No persistence (pure cache, `maxmemory-policy allkeys-lru`) | Optimized for throughput; losing this on restart is a cold-cache, not data loss |
| `redis-broker` | Celery broker + result backend, Alert Streams (durability-critical) | AOF enabled (`appendonly yes`) | Task/alert durability required — losing in-flight tasks or unacked alerts is a real incident |
| `redis-session` | User sessions/permissions cache, rate-limit counters, WS connection-count counters | RDB snapshotting | Session loss forces re-auth (acceptable, infrequent), doesn't need AOF-grade durability but benefits from surviving a restart |

All three are provisioned as **managed Redis with automatic primary/replica failover** (e.g., AWS ElastiCache with Multi-AZ, or equivalent) at minimum for `redis-broker` and `redis-session` — an unavailable broker stalls every background job platform-wide, and an unavailable session store logs out every active user; both are unacceptable single points of failure to run without failover, even at launch scale. `redis-cache` can tolerate a brief cold-start on failover (cache repopulates from source-of-truth on miss) so a simpler managed instance is acceptable there if cost-constrained, but Multi-AZ is still preferred once budget allows (Document 7 §19 cost notes).

**Cache stampede / thundering herd protection (gap identified in architecture review — now specified):** popular symbols (e.g., a viral stock) or expensive queries (screener, prediction) can receive many concurrent requests at the exact moment a cache entry expires, causing a stampede of redundant recomputation/DB load. Mitigated by:
- **Distributed lock on population**: on a cache miss, the first request acquires a short-lived `SETNX`-based lock (`lock:{cacheKey}`, e.g. 5s TTL) and computes the value; concurrent requests for the same key that see the lock held either wait briefly (bounded retry) or serve the just-expired stale value with a `stale: true` marker rather than all recomputing simultaneously.
- **Jittered TTLs**: cache TTLs (screener 5 min, prediction 1 hour) have ±10% random jitter applied per key so that many keys created around the same time don't all expire in the same instant.
- **Backfill-in-progress flag**: historical backfill (Document 5 §11.3) checks a `backfill:inflight:{symbol}` flag before enqueueing a Celery task, so N concurrent requests for a never-before-seen symbol enqueue exactly one backfill job, not N duplicate jobs.

**Cache table (corrected):**

| Data | Cache location | TTL | Invalidation |
|---|---|---|---|
| Latest quote per symbol | `redis-cache` string | Overwritten on every tick (no TTL, always-fresh-or-absent) | N/A — always overwritten |
| Current-day (still-open) OHLCV bar | `redis-cache` | 1 hour, jittered | Invalidated on new tick within the bar period |
| Closed/immutable historical OHLCV bars | `redis-cache`, LRU-evicted (hot window only — no fixed day count; whatever fits under `maxmemory-policy allkeys-lru`) + Postgres (source of truth, full history, never evicted) | No explicit TTL — relies on LRU eviction under memory pressure, cache-aside re-populates from Postgres on miss | Never invalidated (immutable data); eviction is a capacity decision, not a correctness one |
| User session/permissions | `redis-session` hash | Matches access token TTL (15 min) | On logout / role change |
| Prediction results | `redis-cache` (ephemeral) + Mongo (durable source of truth) | 1 hour, jittered, or until next scheduled model run | Explicit invalidation on new `PredictionRun` |
| Screener query results | `redis-cache` (keyed by filter hash) | 5 minutes, jittered | TTL-only (acceptable staleness for screening) |
| Rate limit counters | `redis-session` (sliding window) | Matches window (e.g. 60s) | Auto-expire |
| Celery broker/results, Alert Streams | `redis-broker` | N/A (queue/stream semantics, not cache) | Consumer-acknowledged |

**Cache-aside pattern** used uniformly for genuine caches (`redis-cache`): application code checks Redis first, falls back to DB, populates Redis on miss. No write-through caching for financial data — writes always go to the source of truth (Postgres) first, cache is invalidated/updated after, never the reverse, to avoid cache-DB divergence on money-related data.

**Read-after-write consistency (gap identified in architecture review — now specified):** Document 7 §19.3 prescribes Postgres read replicas for read-heavy queries. Rule: a request that just performed a write (e.g., add holding, then the same response/next request reloads that portfolio) always reads from the **primary**, never a replica — enforced by routing same-request and immediately-following-request reads for a user's own just-mutated resource through a "primary-pinned" DB session. Replicas are used only for genuinely eventually-consistent, cross-user aggregate reads (screener universe, market-wide aggregates) where a few hundred milliseconds of replication lag is invisible to the end user.

### 7.8 Background Jobs (Celery)

| Task | Trigger | Queue |
|---|---|---|
| Historical backfill for new symbol | On-demand (user adds unfamiliar symbol), guarded by `backfill:inflight:{symbol}` flag (§7.7) | `market-data` |
| Nightly full re-sync of fundamentals | Cron (daily, off-market-hours) | `market-data` |
| Generate forecast (LSTM/Prophet/ARIMA ensemble) | Cron (pre-market daily) + on-demand for Pro users | `ml-inference` |
| Sentiment scoring of new news batch | Triggered by news ingestion event | `ml-inference` |
| Portfolio risk recalculation | On holding change + nightly | `ml-inference` |
| Alert evaluation sweep (sharded) | Every 1 min, fanned out into per-shard sub-tasks hashed by `instrument_id` (see revision note below) | `alerts` (high priority, short tasks) |
| Model retraining | Manual trigger / weekly cron | `ml-training` (separate worker pool, higher memory) |
| Email/push notification delivery | Event-triggered | `notifications` |

> **REVISION (post-architecture-review):** the alert evaluation sweep was originally specified as a single unsharded task loading all active alerts every 60 seconds — this creates a self-inflicted periodic load spike and a hard scaling ceiling as the number of active alerts grows. **Fix:** the sweep is now a lightweight scheduler task that partitions active instrument IDs into N shards (hash of `instrument_id` mod shard-count) and enqueues one sub-task per shard onto the `alerts` queue, so evaluation work is spread across the existing worker pool in parallel rather than executed as one large sequential pass, and shard-count scales independently as alert volume grows.

Separate Celery worker pools per queue (`ml-training` workers provisioned with more memory/CPU than `alerts` workers) — this is configured in `docker-compose`/K8s as distinct deployments, not just logical queue names on shared workers, so a slow model retrain never starves alert delivery. `market-data`, `alerts`, and `notifications` queues run as worker processes within the `core-api` deployable (per §7.1's revision); `ml-inference` and `ml-training` run within the `ai-service` deployable.

---

## 8. Database Design

### 8.1 PostgreSQL Schema (Core Relational Data)

```sql
-- ============ IDENTITY & ACCESS ============
CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email             CITEXT UNIQUE NOT NULL,
    hashed_password   TEXT,                      -- NULL if OAuth-only account
    full_name         TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user','pro_user','admin','super_admin')),
    token_version     INTEGER NOT NULL DEFAULT 0,  -- bump to invalidate all sessions
    risk_profile       TEXT CHECK (risk_profile IN ('conservative','moderate','aggressive')),
    email_verified_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE oauth_accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,               -- 'google' | 'github'
    provider_user_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider, provider_user_id)
);

CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id) WHERE revoked_at IS NULL;

CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          TEXT NOT NULL,               -- 'LOGIN','PORTFOLIO_CREATE','ORDER_PLACED', etc.
    resource_type   TEXT,
    resource_id     UUID,
    ip_address      INET,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_logs_user_time ON audit_logs(user_id, created_at DESC);

-- ============ INSTRUMENTS (relational reference data) ============
CREATE TABLE instruments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    exchange        TEXT NOT NULL,
    name            TEXT NOT NULL,
    asset_type      TEXT NOT NULL CHECK (asset_type IN ('equity','etf','index','crypto')),
    sector          TEXT,
    industry        TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD',
    ipo_date        DATE,                          -- NULL if unknown; drives "insufficient history" gating (Doc 4 §10.x revision)
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(symbol, exchange)
);
CREATE INDEX idx_instruments_symbol ON instruments USING btree (symbol);

-- REVISION (post-architecture-review): every market-data/AI endpoint in Document 4 §9.4
-- (quote/bars/fundamentals/forecast/sentiment/recommendation, all keyed by bare `:symbol`)
-- is ambiguous for dual-listed instruments, since `instruments.symbol` is only unique
-- together with `exchange`, not globally. DECISION: for V1, `instruments.symbol` is
-- ADDITIONALLY constrained to be globally unique for the equity/etf/index asset types we
-- actually list at launch (a curated single-exchange-per-symbol universe — e.g., list AAPL
-- against NASDAQ only, not also against a secondary foreign listing). This is enforced via
-- a partial unique index rather than changing the API surface to be exchange-qualified,
-- which would ripple through every route in Document 4. If/when dual-listed coverage
-- becomes a real requirement (post-launch), the API moves to accepting an optional
-- `?exchange=` disambiguator with symbol-only remaining the default (resolving to the
-- canonical primary listing) — tracked as a future ADR (Document 8 §23), not built now.
CREATE UNIQUE INDEX idx_instruments_symbol_global ON instruments(symbol) WHERE is_active = true;

-- OHLCV bars — the highest write/read volume table in the platform; DDL was previously
-- missing despite being referenced narratively in §8.4/Doc 5 §11/Doc 8 Phase 3. Added here.
--
-- IMPLEMENTATION NOTE (Phase 4, disclosed simplification — not an ADR, no schema/contract
-- change): built as a single non-partitioned table. The frozen `PARTITION BY RANGE
-- (bar_time)` + monthly-partition-maintenance-job design below is retained as the target;
-- Phase 4 defers it because (a) no `create_next_partition()` scheduled job exists yet in
-- this codebase (Celery/cron infra for maintenance jobs, distinct from the sync task, is
-- not part of Phase 4's explicit scope) and (b) all reads/writes go through
-- OhlcvBarRepository (src/infrastructure/persistence/postgres/repositories/
-- ohlcv_bar_repository.py), so adding partitioning later requires zero application-code
-- changes — only a migration that converts the table to partitioned and backfills the
-- monthly-partition job. Column/constraint/index shapes below are otherwise implemented
-- exactly as written, including the composite primary key and the interval CHECK.
CREATE TABLE ohlcv_bars (
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    interval        TEXT NOT NULL CHECK (interval IN ('1min','5min','15min','1h','1d','1w')),
    bar_time        TIMESTAMPTZ NOT NULL,          -- start of the bar period, UTC
    open            NUMERIC(20,8) NOT NULL,
    high            NUMERIC(20,8) NOT NULL,
    low             NUMERIC(20,8) NOT NULL,
    close           NUMERIC(20,8) NOT NULL,
    adjusted_close  NUMERIC(20,8) NOT NULL,        -- corporate-action-adjusted, see corporate_actions below
    volume          BIGINT NOT NULL CHECK (volume >= 0),
    is_closed       BOOLEAN NOT NULL DEFAULT true, -- false for the still-forming current-period bar
    source          TEXT NOT NULL,                 -- vendor that supplied this bar, for audit
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (instrument_id, interval, bar_time)
) PARTITION BY RANGE (bar_time);

-- Monthly range partitions (created ahead via a scheduled migration job, not manually per-month)
-- NOT YET IMPLEMENTED (Phase 4) — see the IMPLEMENTATION NOTE above the table definition.
CREATE TABLE ohlcv_bars_2026_07 PARTITION OF ohlcv_bars
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
-- ...additional partitions created by a scheduled `create_next_partition()` maintenance
-- job (runs monthly, creates the following month's partition ahead of time) rather than
-- relying on manual DDL — this is what makes the retention/performance story in Doc 3 §8.4
-- actually implementable, since unpartitioned tables at this write volume degrade badly.
CREATE INDEX idx_ohlcv_bars_instrument_interval_time ON ohlcv_bars(instrument_id, interval, bar_time DESC);

-- Corporate actions — described narratively in Doc 5 §11.4 with no DDL; added here.
-- This is what `adjusted_close` above is computed from.
-- IMPLEMENTED AS WRITTEN (Phase 4) — CorporateActionModel/SqlAlchemyCorporateActionRepository
-- match this exact shape, including the UNIQUE(instrument_id, action_type, ex_date)
-- constraint (verified against real Postgres via integration test, Docker permitting).
CREATE TABLE corporate_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    action_type     TEXT NOT NULL CHECK (action_type IN ('split','dividend','spinoff')),
    ratio           NUMERIC(20,8),                 -- e.g. 4.0 for a 4:1 split; NULL for cash dividends
    cash_amount     NUMERIC(20,8),                 -- for dividends; NULL for splits/spinoffs
    ex_date         DATE NOT NULL,
    announced_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(instrument_id, action_type, ex_date)
);
CREATE INDEX idx_corporate_actions_instrument_exdate ON corporate_actions(instrument_id, ex_date DESC);

-- ============ SCREENER (pre-materialized factor table — see Doc 4 §9.4 revision) ============
-- The Screener previously had zero backing schema despite being a named endpoint. A
-- naive live-computed multi-factor query across instruments+fundamentals+indicators is
-- both slow and, per the security review, a DoS vector (unbounded filter-combination cost).
-- Fix: nightly job materializes one row per active instrument with pre-computed,
-- indexed factor columns; the screener endpoint only ever filters/sorts this table.
CREATE TABLE screener_factors (
    instrument_id       UUID PRIMARY KEY REFERENCES instruments(id),
    price               NUMERIC(20,8),
    market_cap          NUMERIC(24,2),
    pe_ratio            NUMERIC(12,4),
    dividend_yield      NUMERIC(8,4),
    rsi_14              NUMERIC(8,4),
    pct_change_1d       NUMERIC(8,4),
    pct_change_30d      NUMERIC(8,4),
    sma_50              NUMERIC(20,8),
    sma_200             NUMERIC(20,8),
    volume_avg_30d      BIGINT,
    sector              TEXT,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_screener_pe ON screener_factors(pe_ratio);
CREATE INDEX idx_screener_market_cap ON screener_factors(market_cap);
CREATE INDEX idx_screener_sector ON screener_factors(sector);
-- The screener API (Doc 4 §9.4) is restricted to filtering/sorting ONLY on columns that
-- exist here (a fixed whitelist), never arbitrary computed expressions — this is what
-- bounds query cost and closes the algorithmic-complexity gap identified in review.

-- ============ PORTFOLIO CONTEXT ============
CREATE TABLE portfolios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    base_currency   TEXT NOT NULL DEFAULT 'USD',
    is_paper        BOOLEAN NOT NULL DEFAULT true,   -- paper trading vs. tracked-real portfolio
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_portfolios_user ON portfolios(user_id);

CREATE TABLE holdings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    quantity        NUMERIC(20,8) NOT NULL CHECK (quantity >= 0),
    average_cost    NUMERIC(20,8) NOT NULL CHECK (average_cost >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(portfolio_id, instrument_id)
);

CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    instrument_id   UUID REFERENCES instruments(id),      -- nullable as of ADR-0003 (Phase 3):
                                                           -- deposit/withdrawal have no instrument
    type            TEXT NOT NULL CHECK (type IN ('buy','sell','dividend','split','transfer_in',
                                                   'transfer_out','deposit','withdrawal')),
                                                           -- REVISION (Phase 3, ADR-0003): extended
                                                           -- from the original 5 values with
                                                           -- 'split','transfer_in','transfer_out' to
                                                           -- satisfy the explicit founder requirement
                                                           -- for split/transfer transaction tracking.
                                                           -- Additive only — no value removed.
    quantity        NUMERIC(20,8),                        -- nullable as of ADR-0003: split/deposit/
                                                           -- withdrawal don't carry a quantity
    price           NUMERIC(20,8),                        -- nullable as of ADR-0003: split/deposit/
                                                           -- withdrawal don't carry a per-share price.
                                                           -- For 'dividend', this is the PER-SHARE
                                                           -- amount (not a lump sum) — dividend
                                                           -- income = price * quantity.
    fees            NUMERIC(20,8) NOT NULL DEFAULT 0,
    split_ratio     NUMERIC(20,8),                        -- ADR-0003: e.g. 2.0 for a 2:1 split;
                                                           -- NULL for all other transaction types
    related_portfolio_id UUID REFERENCES portfolios(id),  -- ADR-0003: links the two legs of an
                                                           -- internal transfer_in/transfer_out
                                                           -- between two of the user's own
                                                           -- portfolios; NULL for external transfers
                                                           -- and all other transaction types
    cash_amount     NUMERIC(20,8),                        -- ADR-0003: the cash amount moved for
                                                           -- deposit/withdrawal; NULL otherwise
    executed_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_transactions_portfolio_time ON transactions(portfolio_id, executed_at DESC);
-- See docs/architecture/adr/0003-split-transfer-transaction-types.md for full rationale,
-- alternatives considered, and the realized/unrealized gain treatment of transfers.

CREATE TABLE paper_orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    side            TEXT NOT NULL CHECK (side IN ('buy','sell')),
    order_type      TEXT NOT NULL CHECK (order_type IN ('market','limit')),
    quantity        NUMERIC(20,8) NOT NULL CHECK (quantity > 0),
    limit_price     NUMERIC(20,8),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','filled','cancelled','rejected')),
    filled_price    NUMERIC(20,8),
    filled_at       TIMESTAMPTZ,
    idempotency_key TEXT,                          -- see Doc 4 §9.7; scoped per-portfolio below
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()   -- was missing; required so a trigger
                                                          -- can maintain it on status transitions
);
CREATE INDEX idx_paper_orders_portfolio_status ON paper_orders(portfolio_id, status);
-- Idempotency-Key scoping (gap identified in review): unique per portfolio, not globally,
-- since the header value is client-generated and only needs to disambiguate retries of the
-- SAME logical order submission, not collide-proof across all users/portfolios platform-wide.
CREATE UNIQUE INDEX idx_paper_orders_idempotency ON paper_orders(portfolio_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE TRIGGER trg_paper_orders_updated_at BEFORE UPDATE ON paper_orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();  -- shared trigger fn, defined once in Doc 3 §8.1 preamble

-- ============ WATCHLIST CONTEXT ============
-- See ADR-0004 for a scope change to this section (additive columns for
-- multi-watchlist default-tracking, custom ordering, and pinning).
--
-- PHASE 5 IMPLEMENTATION NOTE: built exactly as specified below, plus
-- ADR-0004's 4 additive columns (watchlists.is_default/updated_at,
-- watchlist_items.position/is_pinned) and 2 additive indexes
-- (idx_watchlists_user_default partial unique index, enforced and
-- integration-tested against real Postgres per ADR-0004's design;
-- idx_watchlist_items_watchlist_position for ordered reads). No column
-- below was removed or retyped. `updated_at` is maintained at the
-- application layer (mapper writes the domain entity's computed
-- timestamp), matching portfolios/holdings — no DB trigger, consistent
-- with the rest of this codebase.
CREATE TABLE watchlists (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL DEFAULT 'My Watchlist',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE watchlist_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id    UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(watchlist_id, instrument_id)
);

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    condition_type  TEXT NOT NULL CHECK (condition_type IN ('price_above','price_below','pct_change','rsi_threshold')),
    threshold       NUMERIC(20,8) NOT NULL,
    is_recurring    BOOLEAN NOT NULL DEFAULT false,   -- if true, re-arms after cooldown_minutes instead of one-shot deactivation
    cooldown_minutes INTEGER NOT NULL DEFAULT 0 CHECK (cooldown_minutes >= 0),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    triggered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Missing unique constraint (identified in review): prevents a user from silently
    -- creating N identical duplicate alerts on the same instrument/condition/threshold,
    -- which would otherwise fire N redundant notifications for the same real-world event.
    UNIQUE(user_id, instrument_id, condition_type, threshold)
);
CREATE INDEX idx_alerts_active_instrument ON alerts(instrument_id) WHERE is_active = true;

-- ============ DIVIDEND / SIP / IPO FEATURES (roadmap named these in Doc 8 Phase 9 and
-- Doc 1 §1.2 persona table with zero backing schema/API anywhere — gap closed here) ============
CREATE TABLE dividend_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    amount_per_share NUMERIC(20,8) NOT NULL,
    ex_date         DATE NOT NULL,
    pay_date        DATE,
    frequency       TEXT CHECK (frequency IN ('monthly','quarterly','semi_annual','annual','special')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(instrument_id, ex_date)
);
CREATE INDEX idx_dividend_records_instrument ON dividend_records(instrument_id, ex_date DESC);
-- Dividend Analysis feature (Doc 8 Phase 9) reads this joined with `holdings` to project
-- forward income; SIP Calculator (same phase) is a pure computation over `ohlcv_bars`
-- historical returns + user-supplied contribution schedule — stateless, no dedicated table
-- needed beyond optionally persisting a named "SIP scenario" per user:
CREATE TABLE sip_scenarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instrument_id   UUID NOT NULL REFERENCES instruments(id),
    name            TEXT NOT NULL,
    monthly_amount  NUMERIC(20,8) NOT NULL CHECK (monthly_amount > 0),
    start_date      DATE NOT NULL,
    frequency       TEXT NOT NULL DEFAULT 'monthly' CHECK (frequency IN ('weekly','monthly')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- IPO Analyzer (Doc 8 Phase 9) surfaces upcoming/recent IPOs; sourced from a vendor
-- feed (same ACL pattern as Doc 5 §11.1) and normalized here:
CREATE TABLE ipo_listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id   UUID REFERENCES instruments(id),   -- NULL until the instrument is actually listed/tracked
    company_name    TEXT NOT NULL,
    expected_date   DATE,
    price_range_low  NUMERIC(20,8),
    price_range_high NUMERIC(20,8),
    status          TEXT NOT NULL DEFAULT 'expected' CHECK (status IN ('expected','priced','listed','withdrawn')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============ BILLING (future-ready, structure only) ============
CREATE TABLE subscription_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,          -- 'free','pro','enterprise'
    price_cents     INTEGER NOT NULL DEFAULT 0,
    features        JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE user_subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id         UUID NOT NULL REFERENCES subscription_plans(id),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled','past_due')),
    current_period_end TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 8.2 MongoDB Collections (Document Store)

```javascript
// news_articles
{
  _id: ObjectId,
  headline: String,
  body: String,
  source: String,             // 'reuters', 'bloomberg-rss', etc.
  url: String,
  relatedSymbols: [String],   // denormalized for fast lookup
  publishedAt: ISODate,
  ingestedAt: ISODate,
  rawPayload: Object          // original vendor shape, for audit/reprocessing
}
// Indexes: { relatedSymbols: 1, publishedAt: -1 }, { publishedAt: -1 }

// sentiment_scores
{
  _id: ObjectId,
  articleId: ObjectId,        // ref news_articles
  symbol: String,
  modelVersion: String,       // 'finbert-v1.2'
  sentiment: String,          // 'positive' | 'negative' | 'neutral'
  score: Number,              // -1.0 to 1.0
  confidence: Number,         // 0.0 to 1.0
  computedAt: ISODate
}
// Indexes: { symbol: 1, computedAt: -1 }

// prediction_runs
// REVISION: `instrumentSymbol` (bare string) replaced with `instrumentId` (matches
// Postgres instruments.id) to fix the same dual-listing ambiguity addressed in §8.1's
// instruments table revision, and to make cross-store joins (Mongo prediction ->
// Postgres instrument) unambiguous rather than string-matching on a mutable-in-theory
// display symbol. Storage tiering added (unbounded growth flagged in review).
{
  _id: ObjectId,
  instrumentId: String,       // UUID string, ref Postgres instruments.id — NOT bare symbol
  modelVersion: String,       // 'lstm-v3', 'prophet-v1', 'ensemble-v2'
  horizon: String,            // '1d','7d','30d'
  forecastPrice: Decimal128,
  confidence: Number,
  dataQuality: String,        // 'full' | 'insufficientHistory' | 'partialEnsemble' — see Doc 4 §10.x revision
  predictedAt: ISODate,
  targetDate: ISODate,
  actualPrice: Decimal128,    // backfilled later for accuracy tracking, null until then
  featureSnapshotRef: ObjectId, // ref feature_snapshots — full feature vector stored once, referenced here (not duplicated per prediction, since ensemble members share the same input snapshot)
  shapValues: Object          // explainability payload
}
// Indexes: { instrumentId: 1, predictedAt: -1 }, { targetDate: 1 } (for backfill jobs)
// Storage tiering (gap identified in review — unbounded growth): predictions older than
// 2 years are migrated to cold object storage (S3-compatible, Parquet export) via a
// scheduled job and removed from the hot Mongo collection; accuracy-tracking dashboards
// that need long-range history read from the cold export, not live Mongo queries.

// feature_snapshots (missing collection, referenced narratively in Doc 4 §10.2 but never
// documented as its own collection — added here; this IS the "feature store" and its
// versioning is what prevents train/serve skew, per the ML pipeline revision in Doc 4)
{
  _id: ObjectId,
  instrumentId: String,       // ref Postgres instruments.id
  featureSetVersion: String,  // semver, e.g. 'v3.2.0' — ties to the shared feature registry
                               // library (Doc 4 revision) used by BOTH training and inference
  features: Object,           // { rsi14: 42.1, sma50: 231.0, sentiment7d: 0.12, ... } —
                               // keys are exactly the registered feature names for featureSetVersion
  computedAt: ISODate,
  dataCompleteness: Number    // 0.0-1.0, from Doc 5 §11.3's backfill completeness signal —
                               // now actually consumed downstream (previously computed but unused)
}
// Indexes: { instrumentId: 1, featureSetVersion: 1, computedAt: -1 }
// TTL index: raw per-computation snapshots older than 180 days auto-expire (the durable
// training record lives in the versioned training dataset exports under ml/training/,
// not in this live-serving collection).

// risk_assessments
// REVISION: added explicit index + note on the cross-store FK gap identified in review —
// Mongo cannot enforce a real foreign key against Postgres `portfolios.id`. Integrity is
// enforced at the application layer instead: the RiskAssessment repository's write path
// verifies the portfolio exists (via the Portfolio repository) before persisting, and a
// nightly consistency-check job flags orphaned risk_assessments (portfolioId with no
// matching Postgres row — e.g., a deleted portfolio) for cleanup, since Postgres's
// ON DELETE CASCADE on portfolios has no way to cascade into a different database engine.
{
  _id: ObjectId,
  portfolioId: String,        // ref Postgres portfolios.id — app-layer-enforced FK, see note above
  volatility: Number,
  valueAtRisk95: Decimal128,
  sharpeRatio: Number,
  beta: Number,
  riskScore: Number,          // 0-100 composite
  dataQuality: String,        // 'full' | 'insufficientHistory' — mirrors prediction_runs pattern
  computedAt: ISODate
}
// Indexes: { portfolioId: 1, computedAt: -1 }

// market_data_raw_snapshots  (audit / reprocessing capability)
{
  _id: ObjectId,
  vendor: String,
  endpoint: String,
  requestParams: Object,
  responseBody: Object,
  fetchedAt: ISODate
}
// TTL index: expires after 30 days (auto-cleanup, avoid unbounded growth)
```

### 8.3 Redis Key Schema

> **REVISION:** updated to reflect the 3-instance split (`redis-cache` / `redis-broker` / `redis-session`) from §7.7, and to correct the same "cached indefinitely" contradiction fixed there.

```
# redis-cache instance
quote:{symbol}                     -> Hash {price, volume, change, changePct, timestamp}   (no TTL, overwritten)
quotes:channel:{symbol}            -> Pub/Sub channel
bars:1d:{symbol}:{date}            -> String (JSON OHLCV)   TTL: none, LRU-evicted under memory pressure (closed bars are immutable but not memory-unbounded — see §7.7)
screener:{filterHash}              -> String (JSON results)  TTL: 5 min ± jitter
prediction:{instrumentId}:{horizon} -> String (JSON forecast) TTL: 1h ± jitter
lock:{cacheKey}                     -> String (SETNX-based population lock)  TTL: 5s

# redis-broker instance
celery-broker / celery-results     -> (managed by Celery internally, AOF-persisted)
alerts:stream                       -> Redis Stream (durable, consumer-group "notification-workers")
backfill:inflight:{symbol}          -> String (dedupe flag)   TTL: matches expected backfill job duration

# redis-session instance
session:{userId}:permissions       -> Hash                   TTL: 15 min (matches access token)
ratelimit:{userId}:{endpoint}      -> String (counter)        TTL: window size
ws:conn:{connectionId}:subscriptions -> Set of symbols
ws:count:{userId}                   -> String (counter, concurrent connection cap enforcement)
```

### 8.4 Data Retention & Partitioning Strategy

- `ohlcv_bars`: partitioned by `bar_time` (monthly range partitions, DDL in §8.1) from day one — not deferred to "Phase 7+ once volume justifies it" as originally stated, because this table's write volume from day-one market data ingestion (Document 5 §11) is exactly the profile partitioning exists for; waiting until it's already large makes the initial partitioning migration far more disruptive than provisioning it upfront costs.
- `transactions` and `paper_orders`: partitioned by `created_at` (monthly range partitions) once volume justifies it (Phase 7+) — schema designed to support this from day one (no partitioning-hostile constructs like sequential surrogate keys that would need rework).
- `audit_logs`: retained 1 year hot (Postgres), archived to cold object storage (S3-compatible) beyond that.
- `market_data_raw_snapshots` (Mongo): TTL-indexed, 30-day auto-expiry — raw vendor payloads are for debugging/reprocessing only, not long-term storage (normalized bars in the proper OHLCV store are the long-term record).
- `prediction_runs` (Mongo): predictions older than 2 years migrated to cold object storage (Parquet), removed from hot collection (§8.2 revision).
- `feature_snapshots` (Mongo): TTL-indexed, 180-day auto-expiry on the live-serving collection; durable training-time feature exports live separately under `ml/training/` datasets, versioned independently.
- Historical OHLCV bars: stored in Postgres (`ohlcv_bars`, full DDL in §8.1) rather than Mongo, because this data benefits from relational integrity (FK to `instruments`) and is queried with range predicates that Postgres's partition pruning + btree indexes handle efficiently at scale; Mongo is reserved for genuinely variable-shape documents (news, ML artifacts).

### 8.5 Backup & Disaster Recovery (missing entirely from the original draft — added per architecture review)

No backup/DR strategy existed anywhere in the original 8-document blueprint for any of the three databases, despite Document 1 §2.4 explicitly justifying Postgres specifically on financial-data-integrity grounds — integrity guarantees are meaningless without a recovery story if the underlying storage is lost or corrupted. Specified now:

| Store | RPO (max acceptable data loss) | RTO (max acceptable downtime) | Mechanism |
|---|---|---|---|
| PostgreSQL | ≤5 minutes | ≤1 hour | Continuous WAL archiving + Point-In-Time Recovery (PITR) via managed provider (e.g., RDS/Cloud SQL automated backups with PITR enabled), full daily snapshot retained 30 days |
| MongoDB | ≤1 hour | ≤2 hours | Managed automated snapshot backups (e.g., Atlas continuous backup or equivalent) every hour, retained 14 days; oplog-based point-in-time restore where the managed provider supports it |
| `redis-broker` (Celery/Streams) | ≤15 minutes | ≤30 minutes | AOF persistence (already specified §7.7) + hourly RDB snapshot to object storage; acceptable to lose recent in-flight tasks (they are re-enqueued by upstream retry logic) but not the durable Alert Stream backlog |
| `redis-session` | Best-effort (session loss is acceptable) | ≤15 minutes | RDB snapshot only; a restore that loses recent sessions simply forces affected users to re-authenticate — explicitly not a data-loss incident |
| `redis-cache` | N/A — no backup | N/A | Pure cache; cold-starts and repopulates from source-of-truth on restart, by design |

**Restore drills:** a quarterly scheduled drill (tracked as a recurring checklist item from Phase 10 onward, Document 8 §24) restores the most recent Postgres and MongoDB backups into an isolated environment and runs the integration test suite (Document 6 §16.2) against the restored data — verifying backups are actually restorable, not just "backups exist," which is the failure mode that turns a backup strategy into a false sense of security.

---

*End of Document 3. Continuing in Document 4: API Design and AI/ML Pipeline Architecture.*
