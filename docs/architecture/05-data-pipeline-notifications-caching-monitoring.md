# INVEST IQ — Architecture Blueprint
## Document 5 of N: Data Engineering Pipeline, Notification System, Caching (deep-dive), Logging & Monitoring

> Status: DRAFT — pending founder approval

---

## 11. Data Engineering Pipeline (Market Data Flow)

### 11.1 Vendor Abstraction Layer

The single most important architectural decision in the data layer: **no business logic anywhere in the platform ever references a vendor SDK or vendor-specific field name directly.** Everything goes through a `MarketDataProvider` interface defined in the domain layer.

```python
# domain/market_data/provider_interface.py
class MarketDataProvider(Protocol):
    async def get_quote(self, symbol: str) -> QuoteDTO: ...
    async def get_bars(self, symbol: str, interval: Interval, start: date, end: date) -> list[BarDTO]: ...
    async def get_fundamentals(self, symbol: str) -> FundamentalsDTO: ...
    async def stream_quotes(self, symbols: list[str]) -> AsyncIterator[QuoteDTO]: ...

# infrastructure/market_data/providers/polygon_provider.py
class PolygonProvider(MarketDataProvider):
    """Adapter — translates Polygon's specific JSON shape into internal DTOs."""
    ...

# infrastructure/market_data/providers/alpha_vantage_provider.py
class AlphaVantageProvider(MarketDataProvider):
    """Free-tier fallback — delayed data, aggressive rate limiting."""
    ...

# infrastructure/market_data/providers/yfinance_provider.py
class YFinanceProvider(MarketDataProvider):
    """Development/local-only provider — no API key required, unofficial/unstable,
    never used in production."""
    ...
```

**Practical staged rollout this enables (stated honestly, not overpromised):**
- **Local dev / early prototyping**: `yfinance` — free, no key, good enough to build UI against real-shaped data.
- **Launch (free tier)**: Alpha Vantage or Twelve Data free/low tier — delayed quotes (15-20 min), strict rate limits (pooled across all users via the ingestion service, not per-user, so the platform's aggregate usage must be actively managed against vendor quotas).
- **Growth (paid)**: Polygon.io or IEX Cloud paid tier — real real-time data, WebSocket streaming support, this is what unlocks the "real-time" claim honestly for Pro users.

A `ProviderRouter` selects which provider serves which request based on user tier + data freshness requirement, configured via `FeatureEntitlement`, not hardcoded:

```python
class ProviderRouter:
    def resolve(self, user: User, requirement: DataFreshnessRequirement) -> MarketDataProvider:
        if user.has_entitlement("realtime_data") and requirement.needs_realtime:
            return self._realtime_provider   # Polygon
        return self._delayed_provider         # Alpha Vantage
```

> **PHASE 4 IMPLEMENTATION NOTE (disclosed simplification, no ADR — additive/upgrade-
> compatible, not a redesign):** `src/application/market_data/provider.py` implements
> `HistoricalDataProvider`/`RealtimeQuoteProvider`/`MarketDataProvider` as Protocols exactly
> per this pattern. Two concrete adapters were built and genuinely live-tested against real
> network calls: `YFinanceProvider` (dev-only, exactly as scoped above — confirmed live
> against real AAPL quote + historical bars) and `AlphaVantageProvider` (built against the
> real, live-confirmed `GLOBAL_QUOTE` response shape; `TIME_SERIES_DAILY` built from
> official docs' numbered-key convention but not live-verified since it requires a paid/
> registered API key not available in this environment — the public demo key rejects it,
> confirmed live). `PolygonProvider` was NOT built (no API key/budget for a paid provider
> at this stage; the `MarketDataProvider` Protocol is provider-count-agnostic, so adding it
> later is additive, not a redesign). `ProviderRouter` (`src/application/market_data/
> provider_router.py`) implements ordered failover across the configured provider chain,
> but does NOT yet do entitlement-tier-based routing (`user.has_entitlement(...)`) — no
> `FeatureEntitlement` system exists anywhere in this codebase yet (it is a future-phase
> concept, not part of Market Data Foundation). Upgrade path: `ProviderRouter.resolve()`
> can be extended to accept a `user`/`requirement` parameter and branch on entitlement
> without changing its public failover contract.

### 11.2 Ingestion Pipeline Stages

```
┌────────────┐   ┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────┐
│  Fetch/       │   │  Validate     │   │  Normalize     │   │  Persist        │   │  Publish     │
│  Stream       │──▶│  & Dedupe     │──▶│  (ACL mapping) │──▶│  (Postgres/Mongo)│──▶│  Event        │
└────────────┘   └─────────────┘   └──────────────┘   └───────────────┘   └────────────┘

1. Fetch/Stream: scheduled polling (REST, for free-tier providers, staggered per-symbol
   to respect rate limits — token-bucket scheduler) or persistent WebSocket connection
   (for streaming-capable paid providers).

2. Validate & Dedupe:
   - Reject bars with null/negative prices, volume anomalies beyond N standard deviations
     (circuit breaker against vendor data glitches propagating into predictions)
   - Dedupe by (symbol, timestamp, vendor) — a reconnected WS stream replaying the last
     few ticks must not double-count

3. Normalize (Anti-Corruption Layer): vendor-specific field names/units/timezones mapped
   to internal DTOs. E.g., one vendor returns volume as a string, another as int64 with
   different units for pre-market vs regular session — all resolved here, once.

4. Persist:
   - Live quote → Redis (overwrite)
   - Closed daily/intraday bar → Postgres `ohlcv_bars` (append-only, immutable once the
     bar period has closed)
   - Raw vendor payload → Mongo `market_data_raw_snapshots` (30-day TTL, debugging/audit)

5. Publish Event: `QuoteUpdated` or `BarClosed` to Redis Pub/Sub for downstream consumers
   (core-api's notification module for WS fan-out, ai-service for feature recomputation
   triggers — see Document 3 §7.1's post-review service collapse)
```

> **PHASE 4 IMPLEMENTATION NOTE (disclosed simplification, no ADR — the deferred stages
> have no current consumer in this codebase, so deferring them changes no observable
> behavior; both are additive when built):** `src/infrastructure/market_data/tasks.py`'s
> `run_sync_pipeline()` implements stages 1–3 and the Postgres half of stage 4 exactly as
> described (Fetch via the configured provider → Validate & Dedupe via
> `MarketDataValidationService` [`src/application/market_data/validation_service.py`,
> rejecting non-positive prices, high<low, out-of-range open/close, negative volume, and
> volume anomalies beyond a 50x reference-average threshold — a disclosed simplification of
> "N standard deviations" since a stateless per-bar validator has no rolling-window volume
> history to compute a true stddev from] → Normalize is implicit in the provider adapter's
> DTO mapping → Persist to Postgres `ohlcv_bars` via `SqlAlchemyOhlcvBarRepository`).
> **NOT built**: the Mongo `market_data_raw_snapshots` persistence (stage 4's second half)
> and the Redis Pub/Sub `QuoteUpdated`/`BarClosed` event publish (stage 5) — neither Mongo
> nor a Pub/Sub consumer exists anywhere else in this codebase yet (no WS fan-out module,
> no ai-service), so building the publish side with zero subscribers would be dead code, not
> a functioning pipeline stage. Both stages are structurally independent additions:
> `run_sync_pipeline()` already takes its dependencies as injected parameters specifically
> so a Mongo writer and an event publisher can be added as two more injected calls without
> restructuring the function. Scheduling is via direct Celery task invocation
> (`sync_instrument_bars`), not the token-bucket-scheduler/staggered-polling infrastructure
> described for stage 1 — no scheduler service exists yet either.

### 11.3 Historical Backfill Strategy

When a symbol is requested for the first time (user searches/adds it, or the Screener needs its universe populated):

```
1. Check Postgres `ohlcv_bars` for existing coverage for this symbol.
2. If coverage gap exists (or symbol is entirely new):
   a. Enqueue a Celery backfill task (`market-data` queue).
   b. Task fetches historical range from provider (respecting rate limits — backfill
      jobs run at LOWER priority than live quote polling, so backfill never starves
      real-time data for active users).
   c. Bulk-insert via Postgres COPY (not row-by-row inserts) for performance on large
      historical ranges.
3. API returns available data immediately (even if partial) with a `dataCompleteness`
   field in the response meta, and the frontend shows a subtle "loading more history..."
   state while backfill completes — never blocks the user on a synchronous multi-second
   vendor call.
```

> **PHASE 4 IMPLEMENTATION NOTE (disclosed simplification, no ADR):**
> `GetOhlcvBarsUseCase` (`src/application/market_data/get_ohlcv_bars_use_case.py`)
> implements steps 1 and 3 as described (checks Postgres coverage first, returns a
> `data_completeness: "complete"|"partial"` field in the response). Step 2's backfill is
> **synchronous, not an enqueued Celery task**, on a coverage-gap request — the use case
> directly calls the provider, validates/dedupes, and persists inline before responding,
> rather than returning immediately with a background job in flight. This was a deliberate
> scope reduction for Phase 4 (no async job-status/polling contract exists yet on the
> frontend to support a genuine "loading more history..." progressive-enhancement UX), and
> it does NOT use Postgres `COPY` (uses `INSERT...ON CONFLICT DO UPDATE` bulk upsert
> instead, via `OhlcvBarRepository.save_many()`) since COPY's throughput advantage matters
> at a bulk-historical scale this phase's on-demand single-symbol backfill doesn't reach.
> The separate `sync_instrument_bars` Celery task (§11.2 above) exists for scheduled/
> proactive background sync, independent of this on-demand path. Upgrade path: swapping the
> inline call for `celery_app.send_task(...)` plus a job-status endpoint is additive to
> `GetOhlcvBarsUseCase`'s existing structure, not a rewrite.

### 11.4 Data Quality & Corporate Actions

Stock splits and dividends corrupt naive historical price continuity if not handled — a 4:1 split makes it look like the stock crashed 75% unless adjusted.

```
CorporateAction entity: { instrument_id, action_type ('split'|'dividend'|'spinoff'),
                           ratio, ex_date, announced_at }

On ingestion of a new CorporateAction:
  - Historical bars before ex_date are NOT mutated in place (preserves the actual
    historical record as it was)
  - An `adjusted_close` column is maintained alongside raw `close`, recalculated via
    a backward-adjustment factor cascade whenever a new corporate action is recorded
  - Charts default to adjusted prices (correct for trend analysis); raw prices available
    via a toggle for users who want "what the ticker actually showed that day"
```

> **PHASE 4 IMPLEMENTATION NOTE (disclosed simplification, no ADR):** implemented as
> described for `split` actions — `CorporateAction.backward_adjustment_factor()`
> (`src/domain/market_data/entities.py`) computes the correct factor (e.g. 0.5 for a 2:1
> split, 1/3 for a 3:1 split, 2.0 for a reverse split), and
> `OhlcvBarRepository.apply_adjustment_factor_before_date()` performs the backward-
> adjustment cascade as a bulk UPDATE without mutating raw `close`, exactly per this spec.
> `dividend` actions currently have a `backward_adjustment_factor()` of `1.0` (no price
> adjustment) — genuine total-return dividend adjustment (which requires reinvestment-
> assumption math beyond a simple ratio) was not in the founder's explicit Phase 4 scope
> and is disclosed here rather than silently approximated. The frontend's raw/adjusted
> toggle described in the last line was **not built** in Phase 4 — `PriceChart`/
> `OhlcvChart` currently always render `adjusted_close`/adjusted OHLC values; adding a
> toggle is a frontend-only addition (the backend's `/prices` and `/bars` endpoints already
> return both raw and adjusted fields where applicable, so no API change is needed for it).

---

## 12. Notification System Architecture

### 12.1 Notification Types & Channels

| Type | Trigger | Channels (launch) | Channels (future-ready) |
|---|---|---|---|
| Price alert triggered | Alert evaluation sweep matches condition | In-app + WebSocket push | Email, SMS, mobile push |
| New recommendation available | Recommendation synthesis for watchlisted symbol | In-app | Email digest |
| Portfolio risk threshold breached | Nightly risk recalc | In-app + email | SMS for critical |
| System/account (password changed, new login) | Security-relevant events | Email (always, security-critical) | — |
| AI Assistant async task complete | Long-running assistant tool call finishes | In-app + WS | — |

### 12.2 Delivery Architecture

```
Trigger Event ──▶ NotificationService.create() ──▶ Persist (Postgres `notifications` table)
                                                          │
                                    ┌─────────────────────┼─────────────────────┐
                                    ▼                     ▼                     ▼
                          Check user preferences   Push via WS if user    Enqueue email task
                          (NotificationPreference)  currently connected    (Celery, `notifications`
                                    │                                      queue) if preference
                                    ▼                                      allows + (WS not
                          Respect quiet hours /                           connected OR always-email
                          channel opt-outs                                 type like security)
```

```sql
CREATE TABLE notifications (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}',   -- deep-link data (symbol, portfolioId, etc.)
    read_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;

CREATE TABLE notification_preferences (
    user_id            UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    price_alerts_email BOOLEAN NOT NULL DEFAULT true,
    price_alerts_push  BOOLEAN NOT NULL DEFAULT true,
    digest_frequency   TEXT NOT NULL DEFAULT 'daily' CHECK (digest_frequency IN ('off','daily','weekly')),
    quiet_hours_start  TIME,
    quiet_hours_end    TIME
);
```

### 12.3 Alert Evaluation Engine (Reliability-Critical Path)

Alerts use **Redis Streams** (not Pub/Sub), stored in the `redis-broker` instance specifically (Document 3 §7.7's 3-way Redis split), because alert delivery must be at-least-once/durable — a missed price alert is a real user-facing failure (unlike a missed intermediate quote tick, which is superseded instantly by the next one).

> **REVISION (post-architecture-review):** the original single unsharded sweep-every-60s design was flagged as a self-inflicted periodic load spike and a hard scaling ceiling as active alert volume grows. Fixed below (see also Document 3 §7.8's revision) — the sweep is now a lightweight scheduler that fans out into parallel per-shard sub-tasks rather than one large sequential pass.

```
Every 60s (Celery beat schedule):
  1. Scheduler task partitions active instrument IDs into N shards (hash of
     instrument_id mod shard-count) and enqueues one sub-task per shard onto
     the `alerts` queue — this is the fan-out step that replaces the original
     single unsharded pass.
  2. Each shard sub-task loads its active alerts grouped by instrument_id
     (single query per shard, not N+1).
  3. For each instrument with active alerts, read latest cached quote
     (`redis-cache` instance).
  4. Evaluate condition (price_above/below/pct_change/rsi_threshold).
  5. On trigger: write to `alerts:stream` (Redis Stream, `redis-broker`
     instance) with consumer group "notification-workers" — guarantees the
     event is processed even if the specific worker instance crashes
     mid-processing (another consumer in the group picks it up via XCLAIM
     after the idle timeout; verified by the resilience test suite,
     Document 6 §16.2a).
  6. Mark alert `triggered_at`, set `is_active = false` unless `is_recurring`
     (Document 3 §8.1 revision), in which case it re-arms after
     `cooldown_minutes` instead of deactivating.
```

---

## 13. Caching Strategy — Deep Dive (Supplement to Document 3 §7.7)

### 13.1 Cache Invalidation Decision Tree

```
Is the data immutable once created?
├─ YES (closed OHLCV bar, historical PredictionRun) → cache forever, no invalidation needed
└─ NO → Is it high-write-frequency (quotes)?
         ├─ YES → no explicit invalidation, just overwrite on every write (last-write-wins,
         │        acceptable because staleness window is sub-second)
         └─ NO (portfolio value, risk score) → explicit invalidation on the specific
                  domain event that changes it (HoldingAdded, TransactionRecorded emit
                  a cache-bust for that portfolio's cached summary)
```

> **PHASE 4 IMPLEMENTATION NOTE (disclosed simplification, no ADR):**
> `MarketDataCache` (`src/infrastructure/market_data/cache.py`, backed by the `redis-cache`
> instance per Document 3 §7.7's 3-way split) caches quotes with an explicit **30-second
> TTL**, not the "no explicit invalidation, sub-second staleness via continuous
> overwrite" model above. The sub-second model assumes a continuously-streaming quote
> source (WebSocket) constantly overwriting the cache; Phase 4 has no such stream —
> `GetCurrentPriceUseCase` polls providers on cache miss, not continuously — so a bare
> "last write wins, never expires" cache would go stale indefinitely between polls with no
> safety net. The 30s TTL is the interim safety net for that gap: it forces a fresh
> provider fetch at least every 30 seconds even without an active push source. When
> real-time WebSocket streaming (§11.1's "Growth" tier) is built, the TTL can be removed
> in favor of the pure overwrite model above with zero change to `MarketDataCache`'s public
> interface.

### 13.2 Multi-Level Caching for Portfolio Valuation (concrete example)

Portfolio market value = sum(holding.quantity × current_quote.price) — this is recomputed extremely often (every dashboard load, every WS quote tick for watched symbols) so it needs its own tier:

```
L1: In-memory (per-request, not shared) — avoid recomputing twice within one request
L2: redis-cache instance (Document 3 §7.7's 3-way split), keyed `portfolio:{id}:value`,
    TTL 5s ± jitter — smooths out recomputation under high read concurrency (many
    browser tabs/users viewing the same public data, though portfolio value is private
    so this is really about the same user's multiple concurrent requests, e.g. dashboard
    + mobile web simultaneously), with the SETNX-based stampede lock (§7.7) applied on
    population since a popular multi-holding portfolio's cache expiry could otherwise
    trigger redundant concurrent recomputation
L3: Recomputed on-demand from the redis-cache quote entries (L2 miss) — never falls
    through to the database for the quote itself, since quotes live in redis-cache
    authoritatively. Read-after-write consistency rule (Document 3 §7.7 revision)
    applies: a request immediately following a holding mutation reads from Postgres
    primary, not a lagging read replica, before this cache tier is even consulted.
```

### 13.3 CDN & Edge Caching (Frontend Assets)

- Static assets (JS/CSS/fonts/images, R3F/Spline scene assets) served via CDN with long-lived immutable cache headers (content-hashed filenames from Next.js build).
- Landing page (SSG+ISR) served from CDN edge with 1-hour revalidation.
- API responses are **never** CDN-cached (financial data + per-user auth context) — cache-control headers on all `/api/*` responses explicitly set `no-store` for anything user-scoped, `private, max-age=5` at most for anything quote-adjacent that's already Redis-fresh.

---

## 14. Logging, Monitoring, Error Handling

### 14.1 Structured Logging

All services log structured JSON (never plain strings) via a shared `libs/observability` logger, one log line per event:

```json
{
  "timestamp": "2026-07-21T13:05:00.123Z",
  "level": "INFO",
  "service": "core-api",
  "requestId": "req_9f8a...",
  "userId": "usr_...",           // omitted/redacted for anonymous requests
  "event": "portfolio.transaction.recorded",
  "durationMs": 42,
  "metadata": { "portfolioId": "...", "transactionType": "buy" }
}
```

**Redaction rule (security-critical):** logging middleware has an explicit deny-list of field names (`password`, `hashed_password`, `token`, `authorization`, `ssn`, `cardNumber`) that are automatically redacted (`"[REDACTED]"`) before any log line is emitted, applied recursively to nested objects — this is a wrapper around the logger itself, not something each call site has to remember to do.

### 14.2 Distributed Tracing

`requestId` (generated at BFF) propagates via `X-Request-Id` header through every internal service call and is attached to every log line and every span if/when OpenTelemetry tracing is added (Phase 8+, instrumented but not necessarily backed by a full tracing backend like Jaeger/Tempo until scale justifies the operational cost — the propagation discipline is built in from day one even if the visualization backend is added later).

### 14.3 Error Handling Philosophy

```
Domain layer: raises specific domain exceptions (InsufficientHoldingQuantity,
              InstrumentNotFound) — never generic Exception, never HTTP-aware.

Application layer: catches domain exceptions, may wrap/translate, never swallows silently.

Presentation layer: a single centralized exception handler (FastAPI
              exception_handlers.py) maps domain exceptions → HTTP status + the
              standard error envelope (Document 4 §9.2). Adding a new domain
              exception requires registering its HTTP mapping here — enforced by
              a unit test that asserts every domain exception type has a mapping,
              so a forgotten mapping fails CI rather than surfacing as an
              unhandled 500 in production.

Unhandled/unexpected exceptions: caught by a final catch-all handler, logged with
              full stack trace at ERROR level with requestId, returned to the
              client as a generic "INTERNAL_ERROR" (never leaking stack traces,
              internal paths, or exception messages to the client in production —
              gated by an environment flag so local dev can still see full detail).
```

### 14.4 Monitoring & Alerting (Operational)

| Signal | Tool (self-hostable, cost-conscious for early stage) | Alert threshold example |
|---|---|---|
| Application metrics (latency, error rate, throughput) | Prometheus + Grafana | p99 latency > 1s for 5 min sustained |
| Uptime/health checks | Built-in `/health` + `/ready` endpoints per service, polled by Docker/K8s + external uptime monitor | 2 consecutive failed health checks |
| Celery queue depth/backlog | Flower (Celery monitoring) + Prometheus exporter | Queue depth > 1000 sustained 10 min |
| Error tracking (exceptions with stack traces, grouped) | Sentry (generous free tier, easy self-host alternative: GlitchTip) | New error type first-seen, or error rate spike |
| Infra resource usage (CPU/mem/disk) | Prometheus node-exporter + Grafana | Mem > 85%, disk > 80% |
| **Model concept drift** *(NEW — gap identified in architecture review; Document 4 §10.8a)* | Scheduled PSI computation job + Prometheus exporter | Feature PSI > 0.2, OR live directional accuracy drop > threshold vs. trailing baseline — **pages on-call**, does not wait for weekly review, since a drifted model actively serving degraded predictions is an operational incident |
| **Cache stampede lock contention** *(NEW — gap identified in review; Document 3 §7.7)* | Prometheus counter on lock-wait events | Sustained high lock-wait rate on a single cache key — signals a popular symbol/query needs a longer TTL or pre-warming, not just background info |
| Business metrics (signups, active portfolios, prediction accuracy trend — excluding drift, which now pages per above) | Custom dashboard (Grafana panels backed by Postgres/Mongo queries) | Weekly review, not paged |

**Health check contract (every service implements identically):**

```
GET /health   -> 200 {"status":"ok"}                          (liveness — is the process up)
GET /ready    -> 200 {"status":"ready","checks":{"db":"ok","redis":"ok"}}  (readiness — can it serve traffic)
```

---

*End of Document 5. Continuing in Document 6: Security Architecture, Testing Strategy.*
