# INVEST IQ — Architecture Blueprint
## Document 4 of N: API Design, AI/ML Pipeline Architecture

> Status: DRAFT — pending founder approval

---

## 9. API Design

### 9.1 API Style

REST over JSON for all CRUD/query operations. WebSocket for real-time streams. No GraphQL — deliberately avoided at this stage because the domain's read patterns are well-known and stable (not the sprawling, client-driven, arbitrary-shape query problem GraphQL solves best), and REST keeps caching (HTTP/CDN + Redis) straightforward. This can be revisited if a public developer API product emerges later (Enterprise tier).

### 9.2 Response Envelope (enforced platform-wide, non-negotiable)

> **REVISION (post-architecture-review):** the original envelope made `disclaimer` an *optional* field (`"disclaimer"?:`) on a single generic envelope type. An optional field is exactly the kind of thing that can be accidentally omitted by a developer implementing a new ML-derived endpoint — the one failure mode this field exists to prevent. **Fix: two distinct envelope types**, so a missing disclaimer on an advisory endpoint is a compile-time/schema-validation error, not something only a Phase-10 runtime test catches after the fact.

```typescript
// StandardResponseEnvelope<T> — used by non-advisory endpoints (auth, portfolio CRUD, watchlist, etc.)
{
  "success": true,
  "data": T,
  "meta": {
    "timestamp": "2026-07-21T13:05:00Z",
    "requestId": "req_9f8a..."
  }
}

// AdvisoryResponseEnvelope<T> — used by EVERY endpoint that surfaces a prediction,
// recommendation, sentiment score, or risk assessment. `disclaimer` and `confidence`
// are REQUIRED, non-nullable fields at the schema level (Pydantic model on the backend,
// Zod schema + TS type on the frontend) — omitting them fails validation, not just review.
{
  "success": true,
  "data": T,
  "meta": {
    "timestamp": "2026-07-21T13:05:00Z",
    "requestId": "req_9f8a...",
    "disclaimer": "This information is for educational purposes only and does not constitute financial advice.",
    "modelVersion": "ensemble-v2",
    "dataQuality": "full"   // 'full' | 'insufficientHistory' | 'partialEnsemble' | 'degraded' — see §10.10
  }
}

// Degraded-service variant of AdvisoryResponseEnvelope — used when ai-service is
// unavailable or a model fails to load (see §10.10, gap identified in review: the
// original blueprint's "constructor raises if confidence/explainability missing"
// invariant had no defined behavior for genuine service outage, which would have
// blanked the entire Predictions/Recommendation surface with unhandled 500s)
{
  "success": true,
  "data": null,
  "meta": {
    "timestamp": "2026-07-21T13:05:00Z",
    "requestId": "req_9f8a...",
    "degraded": true,
    "disclaimer": "AI predictions are temporarily unavailable. Showing cached data where available."
  },
  "error": { "code": "ML_SERVICE_UNAVAILABLE", "message": "..." }
}

// Error (both envelope types share this shape when success: false)
{
  "success": false,
  "error": {
    "code": "PORTFOLIO_NOT_FOUND",     // stable machine-readable code
    "message": "Portfolio not found or access denied.",
    "details"?: { /* field-level validation errors, etc. */ }
  },
  "meta": {
    "timestamp": "2026-07-21T13:05:00Z",
    "requestId": "req_9f8a..."
  }
}
```

`requestId` is generated at the BFF layer and propagated through every internal service call header (`X-Request-Id`) for distributed tracing correlation (see Monitoring section, Document 5). A CI-enforced OpenAPI lint rule verifies every route tagged `advisory` in the schema uses `AdvisoryResponseEnvelope`, never `StandardResponseEnvelope` — this is the mechanical enforcement point, not just a naming convention developers are expected to remember.

### 9.3 Versioning

URL path versioning: `/api/v1/...`. A new major version is only introduced for breaking changes; additive fields never bump the version. Deprecated versions get a `Deprecation` + `Sunset` HTTP header (RFC 8594) for at least 90 days before removal.

### 9.4 Core Endpoint Catalog (representative, not exhaustive)

> **REVISION (post-architecture-review):** three gaps fixed: (1) `{symbol}`-keyed market-data/AI routes are retained for URL readability but now resolve through the globally-unique-symbol partial index (Document 3 §8.1 revision) rather than being ambiguous; (2) SIP Calculator, IPO Analyzer, and Dividend Analysis were named as committed Phase 9 roadmap deliverables (Document 8) and as persona-level features (Document 1 §1.2) but had zero corresponding endpoints — added below; (3) Screener and Optimizer endpoints gained explicit complexity bounds (see §9.4a) to close an algorithmic-complexity DoS vector identified in the security review.

```
# Auth
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/oauth/{provider}/callback

# Users / Profile
GET    /api/v1/users/me
PATCH  /api/v1/users/me
PATCH  /api/v1/users/me/risk-profile

# Portfolio
# REVISION (Phase 3 implementation, per ADR-0003 and the founder's explicit
# calculation/CRUD requirements): the catalog below reconciles what was
# originally specified here against what was actually built. Full CRUD
# (PATCH/DELETE) and transaction listing were added since the original
# catalog only had GET/POST; a new GET .../summary endpoint was added to
# serve the founder's explicit calculation list (Total Investment, Current
# Value, P/L, P/L%, Average Buy Price, Realized/Unrealized Gain, Dividend
# Income, Allocation %, Daily Gain/Loss) — this is CURRENT-MOMENT
# calculated data, not a substitute for the historical time-series
# `/performance` endpoint below, which remains unimplemented (depends on
# ohlcv_bars, not yet built — see Document 8 §24's Phase 3/Market Data
# Foundation status note).
GET    /api/v1/portfolios
POST   /api/v1/portfolios
GET    /api/v1/portfolios/{id}
PATCH  /api/v1/portfolios/{id}                           # NEW (Phase 3) — update name/base_currency
DELETE /api/v1/portfolios/{id}                           # NEW (Phase 3)
GET    /api/v1/portfolios/{id}/holdings
GET    /api/v1/portfolios/{id}/summary                   # NEW (Phase 3) — current-moment calculated
                                                          # totals (see revision note above); replaces
                                                          # the informal role /performance might have
                                                          # served for a "headline numbers" view, but is
                                                          # NOT a historical time-series
GET    /api/v1/portfolios/{id}/performance?range=1y      # NOT YET IMPLEMENTED — historical
                                                          # time-series, depends on ohlcv_bars
                                                          # (Document 8 §24's Market Data Foundation
                                                          # phase, not yet built)
POST   /api/v1/portfolios/{id}/transactions              # extended (Phase 3, ADR-0003) to accept
                                                          # type IN ('buy','sell','dividend','split',
                                                          # 'transfer_in','transfer_out','deposit',
                                                          # 'withdrawal') — was ('buy','sell',
                                                          # 'dividend','deposit','withdrawal') only
GET    /api/v1/portfolios/{id}/transactions              # NEW (Phase 3) — paginated, filterable by
                                                          # instrument_id/type/executed_after/
                                                          # executed_before
GET    /api/v1/portfolios/{id}/risk-assessment          # AdvisoryResponseEnvelope — NOT YET IMPLEMENTED
GET    /api/v1/portfolios/{id}/dividend-projection       # NEW — Dividend Analysis feature (Doc 8 Phase 9) — NOT YET IMPLEMENTED

# Watchlist
# See ADR-0004 for a scope change to this section (additive endpoints: create/
# rename/delete watchlist, get-one-with-enriched-items, pin/reorder item).
#
# PHASE 5 IMPLEMENTATION NOTE: all 3 endpoints below built exactly as
# catalogued, plus ADR-0004's additive surface — POST /watchlists (create),
# GET /watchlists/{id} (get-one, WITH enriched items: live price/daily
# change/daily %/market status/delayed indicator via
# WatchlistEnrichmentService orchestrating Phase 4's GetCurrentPriceUseCase
# + GetMarketStatusUseCase — the actual Phase 4/5 integration point),
# PATCH /watchlists/{id} (rename and/or set-default), DELETE /watchlists/{id}
# (delete a whole watchlist), PATCH /watchlists/{id}/items/{itemId}
# (pin/unpin and/or reorder). Unlike /instruments/*, ALL 8 watchlist
# endpoints require bearer-token auth (confirmed live: every endpoint
# returns 401 without a token, and the generated OpenAPI spec shows
# security=true on every one) — watchlists are private per-user resources,
# not public reference data.
GET    /api/v1/watchlists
POST   /api/v1/watchlists/{id}/items
DELETE /api/v1/watchlists/{id}/items/{itemId}

# Alerts
GET    /api/v1/alerts
POST   /api/v1/alerts
DELETE /api/v1/alerts/{id}

# Market Data  (:symbol resolves via the globally-unique-symbol index, Doc 3 §8.1)
GET    /api/v1/instruments/search?q=AAPL
GET    /api/v1/instruments/{symbol}/quote
GET    /api/v1/instruments/{symbol}/bars?interval=1d&range=1y
GET    /api/v1/instruments/{symbol}/fundamentals
GET    /api/v1/instruments/{symbol}/corporate-actions    # NEW — surfaces splits/dividends backing adjusted_close
GET    /api/v1/market/heatmap
GET    /api/v1/market/indices
# PHASE 4 IMPLEMENTATION NOTE (disclosed, no ADR — additive, not a redesign):
# Built exactly as catalogued: GET /instruments/search (route path unified with query param
# `q`; added mid-Phase-4 once the StockSearch frontend component made the gap concrete —
# SearchInstrumentsUseCase is a thin wrapper over InstrumentRepository.search(), which
# already existed since Phase 4 task 5), GET /instruments/{symbol}/quote,
# GET /instruments/{symbol}/corporate-actions. Built with a DIFFERENT path than catalogued:
# GET /instruments/{symbol}/bars?interval=&range= is split into two endpoints —
# GET /instruments/{symbol}/bars (OHLCV, for candlestick charts) and
# GET /instruments/{symbol}/prices (adjusted-close-only points, for line charts) — because
# the frontend's explicit requirement list distinguishes "OHLCV Chart" from "Price Chart"
# as two separate components with two separate data shapes; a single combined endpoint
# would force the line-chart consumer to receive full OHLCV it doesn't need. NEW, not in
# this catalog: GET /market/status (market open/closed/pre-market/after-hours + next_open —
# explicit founder Phase 4 requirement, added the same way GET /portfolios/{id}/summary was
# added in Phase 3: a genuinely useful endpoint the frozen catalog didn't anticipate).
# NOT built (out of Phase 4's explicit scope, no schema/consumer exists yet):
# GET /instruments/{symbol}/fundamentals, GET /market/heatmap, GET /market/indices.
# SECURITY NOTE: all built market-data endpoints are UNAUTHENTICATED (no bearer token) —
# public reference data, consistent with this catalog never annotating /instruments/* or
# /market/* with an auth requirement the way session/portfolio routes implicitly carry one.
# Confirmed via the actual generated OpenAPI spec that no `security` requirement is present
# on these routes. This is a disclosed design decision, not an oversight — flagged as
# needing its own ADR if the founder wants these routes gated behind auth later.

# Screener — bounded (see §9.4a)
POST   /api/v1/screener/query          # body: filter criteria restricted to screener_factors columns (Doc 3 §8.1)

# SIP Calculator / IPO Analyzer  (NEW — named in roadmap, had no endpoints)
POST   /api/v1/sip/calculate                              # stateless computation, body: {instrumentId, monthlyAmount, startDate, endDate}
GET    /api/v1/sip/scenarios                               # user's saved scenarios (sip_scenarios table)
POST   /api/v1/sip/scenarios
DELETE /api/v1/sip/scenarios/{id}
GET    /api/v1/ipo/listings?status=expected                # ipo_listings table

# Predictions (AI/ML) — all AdvisoryResponseEnvelope
GET    /api/v1/instruments/{symbol}/forecast?horizon=7d
GET    /api/v1/instruments/{symbol}/forecast/history     # for backtest/accuracy display
GET    /api/v1/instruments/{symbol}/recommendation       # buy/sell/hold + confidence + SHAP

# Sentiment — AdvisoryResponseEnvelope
GET    /api/v1/instruments/{symbol}/sentiment
GET    /api/v1/news?symbol=AAPL&page=1

# Risk & Optimization — bounded (see §9.4a), AdvisoryResponseEnvelope
POST   /api/v1/portfolios/{id}/optimize   # body: constraints (risk tolerance, sector caps)

# Paper Trading
POST   /api/v1/portfolios/{id}/paper-orders     # requires Idempotency-Key header
GET    /api/v1/portfolios/{id}/paper-orders

# AI Assistant — token-budgeted (see §9.6a)
POST   /api/v1/assistant/sessions
POST   /api/v1/assistant/sessions/{id}/messages   # SSE streamed response
GET    /api/v1/assistant/sessions/{id}/messages

# Notifications
GET    /api/v1/notifications
PATCH  /api/v1/notifications/{id}/read
GET    /api/v1/realtime/token             # short-lived WS connect token

# Admin
GET    /api/v1/admin/users
PATCH  /api/v1/admin/users/{id}/role
GET    /api/v1/admin/model-versions
POST   /api/v1/admin/model-versions/{id}/activate         # now supports rollout_percentage, see §10.8 revision
POST   /api/v1/admin/model-versions/{id}/rollback          # NEW — see §10.8 revision
```

### 9.4a Complexity Bounds on Compute-Heavy Endpoints (gap identified in security review — no bound existed on Screener or Optimizer request cost)

- **Screener** (`POST /screener/query`): filter conditions capped at 8 per request; filterable/sortable fields restricted to the fixed whitelist of `screener_factors` columns (Document 3 §8.1) — no arbitrary computed expressions accepted, so query cost is bounded by construction, not just by the existing 5-minute result cache (which only helps repeated *identical* queries, not many distinct expensive ones).
- **Portfolio Optimizer** (`POST /portfolios/{id}/optimize`): bounded to portfolios with ≤100 holdings (a portfolio a retail user would realistically hold; larger portfolios return `422 OPTIMIZATION_SCOPE_TOO_LARGE` with guidance to optimize a sub-selection); the underlying convex solver (Document 4 §10.6) runs with an explicit iteration/wall-clock timeout (10s), and — unlike the original synchronous design — is now dispatched through the same async Celery task queue pattern already used for forecasts (`ml-inference` queue) rather than blocking a request thread, with the client polling or receiving the result via the existing SSE/WS channel.
- **Recommendation synthesis** (`GET /instruments/{symbol}/recommendation`): reads only pre-computed `PredictionRun`/`SentimentScore`/`RiskAssessment` records (never triggers synchronous on-demand computation of any of them) — a cache-miss here returns the last available cached synthesis with a `dataQuality: "stale"` marker rather than compute inline, bounding this endpoint's cost to a handful of reads regardless of load.

### 9.5 Pagination, Filtering, Sorting (uniform convention)

```
GET /api/v1/news?page=1&pageSize=20&sort=-publishedAt&symbol=AAPL

Response meta additionally includes:
"pagination": { "page": 1, "pageSize": 20, "totalItems": 483, "totalPages": 25 }
```

Cursor-based pagination (`?cursor=...`) is used instead for high-frequency/append-only feeds (news, notifications) to avoid page-drift under concurrent writes; offset pagination is reserved for stable, bounded collections (user's own portfolios, watchlists).

### 9.6 Rate Limiting

| Tier | Limit |
|---|---|
| Anonymous (landing page previews) | 20 req/min per IP |
| Free authenticated user | 100 req/min |
| Pro user | 500 req/min |
| Internal service-to-service | Not rate-limited by user tier; protected by circuit breakers instead, plus a coarse secondary per-service ceiling (Document 6 §15.1 revision) so a compromised service-identity token can't bypass end-user limits by calling internal APIs directly |

Enforced via Redis sliding-window counters at the BFF layer; response includes standard headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. Exceeding the limit returns `429` with the standard error envelope, `code: "RATE_LIMIT_EXCEEDED"`.

### 9.6a AI Assistant Cost Control (missing entirely from the original draft — added per architecture review)

Document 1 §1.4 promises "AI assistant unlimited" for Pro-tier users. As originally written, the rate limits above are **request-count** based, which does not bound actual LLM cost — a single assistant message can trigger a multi-step tool-calling loop (Document 3 DDD §3.1 `ConversationSession`/`ToolInvocation`) whose token consumption varies enormously per request. Left unbounded, this is a real, uncapped spend risk, not a hypothetical one.

- **Per-user token budget**: tracked in `redis-session` (`assistant:tokens:{userId}:{billingPeriod}`), decremented per LLM call (input + output tokens). "Unlimited" for Pro is redefined precisely as *no hard cutoff mid-conversation* but a **soft daily cap** past which responses include a note that usage is high and the tool-calling loop depth is reduced (fewer speculative tool calls per turn) — this keeps the product promise honest while bounding worst-case cost.
- **Max tool-call-loop iterations**: hard cap (e.g., 8 tool calls per single user message) on the assistant's own agentic loop, independent of the token budget — prevents a pathological prompt from causing an unbounded number of tool invocations against Portfolio/Market Data/Recommendation/Risk services.
- **LLM circuit breaker**: distinct from the internal-service circuit breaker (Document 7) — if the upstream LLM provider's latency/error rate degrades, the assistant surfaces a degraded-service message rather than retrying indefinitely and multiplying cost.
- **Prompt injection (missing from the threat model in Document 6 §15.1 — added there and referenced here)**: the assistant's tool-calling layer re-authorizes every tool invocation through the exact same ownership/RBAC guards used by the REST API (Document 3 §7.5) — a prompt cannot cause the assistant to call `get_portfolio(otherUsersPortfolioId)` successfully regardless of what the LLM is convinced to attempt, because authorization is enforced at the tool-execution boundary, not trusted from the LLM's own reasoning.

### 9.7 Idempotency

State-mutating endpoints that could be double-submitted (order placement, transaction recording) accept an `Idempotency-Key` header; the server caches the response for that key for 24h in Redis and returns the cached result on retry instead of double-processing — critical for paper orders where a network retry must never create two trades. Scoping (gap identified in review): the key is unique **per portfolio** (Document 3 §8.1's `idx_paper_orders_idempotency`), not globally — a client-generated key only needs to disambiguate retries of the same logical submission, not collide-proof across the entire platform.

---

## 10. AI/ML Pipeline Architecture

### 10.1 Guiding Principle

**No model output reaches a user without: (1) a confidence score, (2) an explainability payload, (3) a model version tag, (4) tracked accuracy history.** This is enforced structurally — the `Forecast` and `Recommendation` domain entities have these as *required* fields, not optional ones; a `PredictionRun` cannot be persisted without them (constructor/validation raises).

> **REVISION (post-architecture-review):** this invariant, as originally stated, had no defined behavior for two real operational scenarios: (a) the `ai-service` being down/unreachable, and (b) an instrument with insufficient history to run the full model suite (e.g., a stock that IPO'd last week). Both are addressed structurally below (§10.1a, §10.10) rather than left to be discovered as production incidents — a strict "never omit these fields" rule without a defined degraded/insufficient-data path just means the system throws unhandled errors instead of gracefully saying "we don't have enough data yet," which is a worse user experience for exactly the cases (new IPOs) the roadmap's own IPO Analyzer feature (Document 8 Phase 9) is supposed to serve.

### 10.1a Minimum Data Requirements & Sparse-Data Handling (gap identified in review — new IPO / insufficient history)

Every model family has a stated minimum data requirement below which it is **excluded from the ensemble for that instrument**, rather than run against statistically meaningless input:

| Model/Signal | Minimum history required | Behavior below threshold |
|---|---|---|
| LSTM (60-day lookback) | 90 trading days | Excluded from ensemble; ensemble falls back to Prophet+ARIMA+XGBoost only |
| Prophet | 30 trading days | Excluded below this; degrades gracefully with wider uncertainty bands as data grows |
| ARIMA | 20 trading days | Excluded below this |
| XGBoost/LightGBM/CatBoost | 20 trading days (needs enough rows to have engineered features at all) | Excluded below this; falls back to fundamentals-only heuristic scoring if even this isn't met |
| SMA200/RSI14/technical indicators | Matches indicator's own window (e.g., 200 days for SMA200) | Indicator omitted from the feature vector entirely (not computed as a misleading partial value) rather than silently using a shorter, non-standard window |
| Risk Engine (volatility/beta/VaR) | 20 trading days minimum for any estimate; 252 days (1yr) for a "stable" confidence tier | Below 20 days: `RiskAssessment.dataQuality = 'insufficientHistory'`, riskScore still computed but flagged; the composite score does not silently pretend to be as reliable as a mature stock's |
| Sentiment aggregation | No minimum (works from day one via news alone) but confidence-weighted by article volume — a symbol with 1 article gets a wide-uncertainty sentiment score, not a false-confident single-article-driven one | N/A — always available, confidence scales with volume |
| Portfolio Optimizer covariance estimation | 60 trading days per holding for a reliable covariance matrix | Holdings below this threshold use a shrinkage estimator (blending toward a sector-average covariance) rather than a noisy sample covariance from too few observations |

Every `PredictionRun`, `RiskAssessment`, and `Recommendation` carries a `dataQuality` field (`'full' | 'insufficientHistory' | 'partialEnsemble'`, Document 3 §8.2 revision) — this is a **disclosed state, not a bypass of the disclaimer invariant**: `insufficientHistory` predictions still carry a confidence score (correctly low) and an explainability payload (correctly noting which models were excluded and why), they are simply honest about reduced reliability rather than either refusing to answer or pretending full confidence. `Document 5 §11.3`'s `dataCompleteness` signal (previously computed but never consumed by anything) now directly feeds this gating decision — the ingestion pipeline's completeness tracking and the ML pipeline's model-selection logic are connected rather than parallel, disconnected concerns.

### 10.1b Service Degradation & Fallback (gap identified in review — no fallback existed for ai-service downtime)

If `ai-service` is unreachable or a specific `ModelVersion` artifact fails to load at inference time, `core-api` does not propagate an unhandled 500 to the client. Instead:

- The endpoint returns the `AdvisoryResponseEnvelope`'s degraded variant (§9.2 revision): `meta.degraded: true`, `error.code: "ML_SERVICE_UNAVAILABLE"`, and `data` populated with the **last successfully cached** prediction/recommendation for that instrument if one exists within a bounded staleness window (24h), clearly marked `dataQuality: 'stale'` — otherwise `data: null`.
- **Rules-based features remain available independently of ai-service health**: Candlestick Pattern Detection (§10.7) is a deterministic rules engine with no ML service dependency, and stays fully functional during an ai-service outage — the frontend's stock-details page does not go blank, only the ML-derived panels (Forecast, Recommendation, Sentiment) show the degraded state.
- **Canary rollout + auto-rollback for model promotion** (closes a related gap in §10.8): a newly promoted `ModelVersion` is not an instant 100%-traffic cutover — see §10.8 revision below.

### 10.2 Prediction Pipeline (Price Forecasting)

```
┌──────────────┐    ┌───────────────────┐    ┌────────────────────┐    ┌────────────────┐
│ Feature        │    │  Model Ensemble    │    │  Post-Processing    │    │  Persistence     │
│ Engineering    │───▶│  Inference          │───▶│  + Explainability    │───▶│  + Serving        │
└──────────────┘    └───────────────────┘    └────────────────────┘    └────────────────┘

1. Feature Engineering (per symbol, scheduled + on-demand):
   - Price-derived: returns, log-returns, rolling volatility, moving averages (SMA/EMA 20/50/200)
   - Technical indicators: RSI, MACD, Bollinger Bands, Stochastic Oscillator, ATR
   - Volume-derived: OBV, volume moving average, relative volume
   - Fundamental (lower frequency): P/E, EPS growth, debt/equity, sector-relative valuation
   - Sentiment (from Sentiment Pipeline output): rolling 7-day sentiment score
   - Macro context: sector index correlation, VIX level
   - Minimum-data gating applied here per §10.1a — indicators/features below their
     window requirement are omitted from the vector, not computed on a truncated window.
   → Written to feature store (Mongo `feature_snapshots` collection, Document 3 §8.2)

   REVISION (feature store versioning — gap identified in review): the original claim
   that "computedAt + feature set version... prevents train/serve skew" was an assertion,
   not a mechanism. Concretely: feature definitions (exact formula, window size, input
   columns for every named feature like `rsi14`, `sma50`) live in a single shared library
   (`libs/domain_common/features/registry.py`) imported identically by BOTH the training
   pipeline (`ml/training/`) and the inference pipeline (`ai-service`) — neither side
   reimplements feature calculation independently. Each registry entry is content-hashed;
   `featureSetVersion` (semver) is bumped only when the registry's hash changes, and a
   `ModelVersion` records which `featureSetVersion` it was trained against (new FK-like
   reference field on `ModelVersion`, §10.8). A CI check fails the build if inference code
   attempts to serve a model against a `featureSetVersion` newer/older than what it was
   trained on without an explicit compatibility override — this is what makes train/serve
   skew a caught build-time error instead of a silent accuracy degradation discovered
   weeks later.

2. Model Ensemble Inference:
   - LSTM (sequence model): captures temporal patterns over 60-day lookback window
   - Facebook Prophet: captures seasonality/trend, robust baseline, handles missing data well
   - ARIMA: classical statistical baseline, useful for short-horizon, low-volatility regimes
   - XGBoost/LightGBM/CatBoost (gradient boosted trees): trained on the full engineered
     feature set (not just price sequence) — captures fundamental/sentiment interactions
     the sequence models can't see directly
   - Per-model-family minimum data thresholds from §10.1a applied — models lacking
     sufficient history are excluded from this instrument's ensemble, not run regardless.
   - Per-member inference timeout (gap identified in review — no latency-spike handling
     existed): each ensemble member call has an independent timeout (e.g., 2s); a member
     that times out is excluded from that specific inference run (not the whole request
     failing), and the resulting ensemble is flagged `dataQuality: 'partialEnsemble'` with
     a correspondingly reduced confidence score — a slow LSTM inference degrades gracefully
     into "we used 3 of 4 models, confidence adjusted down," not a failed request.
   - Ensemble combination: weighted average where weights are themselves learned via a
     concretely-specified stacking meta-model (see §10.2a below — this was previously a
     single unimplementable sentence, now fully specified).

2a. Stacking Meta-Model — Concrete Specification (gap identified in review: the original
    one-sentence description had no architecture, no regime definition, no dependency
    tracking, and no fallback for insufficient training data):
   - **Architecture**: a lightweight linear stacker (ridge regression, not another deep
     model — avoids stacking model complexity on top of ensemble complexity) with inputs
     = [each base model's point forecast, each base model's own historical rolling
     directional accuracy for this (symbol_sector, volatility_regime) bucket] and output
     = the blend weight per base model, constrained to sum to 1 and be non-negative
     (softmax-parameterized to guarantee this without a separate constraint solver).
   - **Regime definition (concrete, not hand-wavy)**: volatility_regime is a 3-bucket
     classification (low/medium/high, defined by trailing-30-day realized volatility
     percentile within the instrument's own history) computed deterministically — not a
     learned clustering, so it's auditable and stable.
   - **New entity**: `StackingModelVersion` — separate from base `ModelVersion` records,
     with an explicit `base_model_version_ids: list[UUID]` dependency list, so retiring or
     replacing a base model version is a tracked, visible dependency change to the
     stacker, not a silent input swap.
   - **Insufficient training samples fallback**: if fewer than 50 historical (bucket,
     outcome) samples exist for a given (symbol_sector, volatility_regime) combination —
     the realistic case for a newly covered sector or in the platform's early months
     before enough backtested history accumulates — the stacker falls back to a static,
     hand-set default weighting (equal-weight or a documented heuristic prior) rather than
     fitting a stacker on too little data and overfitting to noise.
   - **Validation requirement**: the stacked ensemble is only considered viable if it
     beats the single best-performing base model on held-out backtest data (Document 6
     §16.4's existing baseline-comparison principle, extended to apply to the stacker
     itself, which the original blueprint never explicitly required).

3. Post-Processing + Explainability:
   - Confidence score derived from: (a) ensemble member agreement/variance (low variance
     across models = higher confidence), (b) historical accuracy of this model version
     for this symbol/sector over trailing 90 days, (c) data recency/completeness penalty
     (now concretely sourced from §10.1a's dataQuality gating and Document 5 §11.3's
     dataCompleteness signal, rather than an unspecified penalty term)
   - SHAP values computed for the tree-based ensemble member (SHAP is natively efficient
     for tree models via TreeExplainer) — gives per-feature attribution: "RSI oversold
     contributed +0.12, negative sentiment contributed -0.08" etc.
   - LIME used as a secondary/fallback explainer for the neural (LSTM) component where
     SHAP's KernelExplainer would be too slow for real-time serving.

4. Persistence + Serving:
   - Immutable PredictionRun written to Mongo (never overwritten), `dataQuality` and
     `featureSnapshotRef` populated per the revisions above
   - Cached in `redis-cache` (Document 3 §7.7 revision) for fast repeated reads within
     the cache window, with stampede protection (distributed lock, jittered TTL)
   - A separate scheduled job later backfills `actualPrice` once the target date passes,
     enabling continuous accuracy tracking per model version — this is what powers the
     "Predictions > History" UI showing real historical accuracy, not just current forecasts,
     AND feeds the concept drift monitoring in §10.8a below.
```

### 10.3 Sentiment Pipeline

```
News/Social Ingestion ──▶ Deduplication ──▶ Symbol Extraction (NER) ──▶ FinBERT Scoring ──▶ Aggregation
```

1. **Ingestion**: scheduled polling of news APIs/RSS + (future) social sources, normalized into `news_articles` (Mongo).
2. **Deduplication**: near-duplicate detection (title similarity hashing) since multiple sources often republish the same wire story — prevents sentiment double-counting.
3. **Symbol extraction**: NER model (or simpler ticker-symbol/company-name matching against the `instruments` reference table as a fast-path, falling back to a proper NER model for ambiguous mentions) tags `relatedSymbols`.
4. **FinBERT scoring**: domain-specific BERT fine-tuned on financial text (not generic sentiment models — "shares fell on strong earnings due to profit-taking" is not generically negative despite the word "fell") produces positive/negative/neutral + confidence.
5. **Aggregation**: rolling time-windowed sentiment score per symbol (1-day, 7-day, 30-day decayed average) is what actually feeds the Recommendation and Prediction pipelines — raw per-article scores are too noisy to use directly. Per §10.1a, aggregation confidence is **volume-weighted**: a symbol with a single recent article produces a wide-uncertainty sentiment score rather than a falsely-confident single-article-driven one; the confidence weighting formula is `confidence = min(1.0, article_count_7d / target_volume)` where `target_volume` (e.g., 10 articles/week) is the point past which additional volume stops meaningfully increasing confidence.

### 10.4 Recommendation Synthesis (Buy/Sell/Hold)

The `Recommendation` context does not run its own ML model — it is a **rules + weighted-scoring synthesis layer** over the outputs of Prediction, Sentiment, and Risk:

```
score = w1 * normalized(forecast_direction_and_magnitude)
      + w2 * normalized(sentiment_trend)
      + w3 * normalized(technical_signal_confluence)   # e.g. RSI+MACD+MA crossover agreement
      + w4 * normalized(fundamental_valuation_signal)
      - w5 * risk_penalty(instrument_volatility, user_risk_profile_mismatch)

verdict = "buy" if score > threshold_buy
        else "sell" if score < threshold_sell
        else "hold"

confidence = f(ensemble_agreement, data_recency, historical_recommendation_accuracy)
```

Weights (`w1..w5`) are per-user-risk-profile-adjustable (a conservative user's threshold for "buy" is stricter and weights fundamentals/stability higher; an aggressive user's weights favor momentum/technical signals) — this is a deliberate design choice so the same underlying data produces personalized, not one-size-fits-all, verdicts. Weights are versioned config, not hardcoded, so they can be tuned/A-B tested without a code deploy.

Every `Recommendation` persists the full breakdown (each `wN * normalized(...)` term) as its `ExplainabilityPayload` — the UI's "why this recommendation" panel renders this breakdown directly, it is not a separate approximation of the real logic.

### 10.5 Risk Engine

```
Inputs: Portfolio holdings + historical returns of each holding + correlation matrix
Outputs: RiskAssessment (volatility, VaR95, Sharpe ratio, beta vs. benchmark, composite riskScore 0-100)

Calculation approach:
- Historical volatility: annualized stddev of daily log returns per holding, portfolio-weighted
  with covariance matrix (not naive weighted average — accounts for diversification benefit/
  concentration risk properly)
- Value at Risk (95%): historical simulation method (empirical distribution of past portfolio
  returns) — chosen over parametric VaR because it doesn't assume normally-distributed returns
  (financial returns are famously fat-tailed; parametric VaR understates tail risk)
- Sharpe Ratio: (portfolio return - risk-free rate) / portfolio volatility, risk-free rate
  sourced from current T-bill rate (configurable data point, updated periodically)
- Beta: covariance(portfolio returns, benchmark returns) / variance(benchmark returns),
  benchmark = S&P 500 by default, user-selectable
- Composite riskScore: a 0-100 normalized blend of the above + concentration risk
  (Herfindahl-Hirschman Index on position sizing) + sector concentration
```

### 10.6 Portfolio Optimization

Modern Portfolio Theory (Markowitz mean-variance optimization) as the baseline engine, with practical constraints layered on top (real users can't hold fractional-percent allocations sensibly, and pure MPT output is often unintuitive/concentrated):

```
Objective: maximize Sharpe ratio subject to:
  - sum(weights) == 1
  - weight[i] >= 0                          (no shorting in paper/retail context)
  - weight[i] <= max_position_size          (concentration cap, e.g. 25% default, user-adjustable)
  - sector_weight[s] <= max_sector_exposure (diversification constraint)
  - matches user's declared risk_profile's target volatility band

Solved via convex optimization (scipy.optimize / cvxpy) — this is a well-posed convex problem
given the constraints above, so a global optimum is guaranteed and solvable efficiently even
for portfolios with dozens of holdings (bounded to ≤100 holdings per request, §9.4a).
Holdings with less than 60 trading days of history use a shrinkage-estimated covariance
(blended toward sector-average) per §10.1a rather than a noisy sample covariance from too
few observations. Solver runs with an explicit 10-second wall-clock timeout, dispatched via
the async task queue (§9.4a) rather than blocking a request thread.

Output: AllocationSuggestion — target weight per holding + expected return/volatility/Sharpe
of the suggested portfolio vs. current, plus a diff (what to buy/sell/rebalance and by how much)
```

### 10.7 Candlestick Pattern Detection

Rule-based pattern matching (not ML) over OHLCV sequences — deliberately not a black box here, because candlestick patterns are literally defined by explicit geometric rules (body/wick ratios, relative positioning across N candles), so a rules engine is both more accurate and more explainable than training a classifier to rediscover geometry:

```
Patterns detected: Doji, Hammer, Shooting Star, Engulfing (bullish/bearish),
Morning Star, Evening Star, Three White Soldiers, Three Black Crows, Marubozu

Each pattern match includes: pattern name, candle indices matched, reliability
classification (historically documented reliability tier: strong/moderate/weak reversal
or continuation signal) — sourced from established technical analysis literature,
displayed as-is, not claimed as a proprietary discovery.
```

### 10.8 Model Versioning & Lifecycle

```
ModelVersion entity: { id, family ('lstm'|'prophet'|'arima'|'xgboost'|'finbert'),
                        version_tag, trained_at, training_data_range,
                        feature_set_version,          -- NEW, ties to §10.2's feature registry
                        validation_metrics (RMSE/MAE/directional_accuracy),
                        status ('training'|'validating'|'canary'|'active'|'retired'),  -- 'canary' added
                        rollout_percentage,            -- NEW, 0-100
                        artifact_location }

Lifecycle: train (offline, ml/training/) → evaluate against held-out validation set +
           walk-forward backtest → if metrics beat current active version by a defined
           margin → admin promotes to 'canary' at a small rollout_percentage (e.g., 5%,
           deterministically bucketed by hashing user_id so a given user's experience is
           stable rather than flickering between versions per-request) → monitored against
           the active version's live accuracy/error-rate for a minimum soak period → admin
           (or an automated policy once trust is established) increases rollout_percentage
           incrementally toward 100%, at which point status becomes 'active' and the
           previous 'active' version moves to 'retired' but is NOT deleted (needed for
           reproducing/auditing past predictions that were made using it).

REVISION (canary rollout + auto-rollback — gap identified in review): the original
lifecycle was an instant 100%-traffic cutover on promotion with no staged validation
against real live traffic and no automatic safety net. The canary stage above closes
this. Auto-rollback: if a canary version's live directional accuracy over its soak
window drops more than a configured threshold below the currently-active version's
trailing accuracy, `rollout_percentage` is automatically reset to 0 and an alert fires
to the admin channel (Document 5 §14.4) — a bad model does not require a human to notice
a problem before traffic is pulled back, only before it's promoted further.
```

Model artifacts are stored in object storage (S3-compatible), referenced by path in the `ModelVersion` record — never committed to git, never bundled into Docker images directly (images pull the active artifact at container start, enabling model updates without a full redeploy).

### 10.8a Concept Drift Monitoring (missing entirely from the original draft — added per architecture review)

The original blueprint (referenced in Document 6 §16.4) only described **lagging** drift detection — comparing `actualPrice` (backfilled after the fact) against past predictions to catch accuracy degradation that has already happened. This misses **leading** indicators that would catch drift before it manifests as visible accuracy loss:

- **Feature distribution drift**: for each `featureSetVersion`, the training-time distribution of every feature is captured as a reference histogram. In production, a scheduled job computes Population Stability Index (PSI) between the reference distribution and the trailing 30-day live distribution for each feature; a PSI above a standard threshold (0.2, indicating significant distribution shift) flags that feature as drifted.
- **Alerting integration**: model drift is added as its own row in Document 5 §14.4's monitoring/alerting table — `PSI > threshold` or `live directional accuracy drop > threshold` both page (not just "weekly review, not paged" as the original table implied for business metrics generally) since a drifted model actively serving degraded predictions to users is an operational incident, not a business-metrics curiosity.
- **Action on drift detection**: automatically flags the affected `ModelVersion` for retraining review in the Admin Panel (does not automatically retrain or auto-promote a retrained replacement without human validation — retraining triggers the same canary lifecycle above, never skips it).

### 10.9 Explainable AI — SHAP/LIME Integration Detail

```python
# ai-service/src/infrastructure/ml/explainability/shap_explainer.py
class ShapExplainerService:
    def __init__(self, model: XGBoostModel):
        self._explainer = shap.TreeExplainer(model.underlying)

    def explain(self, feature_vector: FeatureVector) -> ExplainabilityPayload:
        shap_values = self._explainer.shap_values(feature_vector.to_array())
        contributions = [
            FeatureContribution(name=feature_vector.names[i], value=float(shap_values[i]))
            for i in range(len(shap_values))
        ]
        contributions.sort(key=lambda c: abs(c.value), reverse=True)
        return ExplainabilityPayload(
            top_contributions=contributions[:8],   # top 8 for UI readability
            base_value=float(self._explainer.expected_value),
            method="shap_tree_explainer",
        )
```

The UI's `ShapExplainer` component (Document 2, `features/predictions/components/`) renders this as a horizontal waterfall/bar chart — positive contributions in emerald (`#10B981`), negative in danger red (`#EF4444`), matching the platform's semantic color usage everywhere else risk direction is shown, for visual consistency.

---

*End of Document 4. Continuing in Document 5: Data Engineering Pipeline (Market Data Flow) and Notification System Architecture.*
