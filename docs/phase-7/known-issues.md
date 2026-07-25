# Phase 7 — Known Issues

Issues and disclosed scope decisions identified during Phase 7 (Hybrid AI & Machine Learning Engine) that remain unresolved or are deliberate, documented boundaries — not defects. Follows the same category scheme used in `docs/phase-1/known-issues.md` (C = environment limitations, D = external tooling limitations) plus a new category for this phase's disclosed scope decisions.

## Category A — Security-Relevant Scope Notes (new this phase, disclosed proactively)

### A1. ai-service's REST API is entirely unauthenticated, including `/train` and `/retrain`
**What:** No endpoint under `/api/v1/ml/*` validates a bearer token or any other credential. Any client that can reach ai-service's base URL can call `POST /train`, `POST /retrain`, `POST /predict`, etc. with no authorization check whatsoever.
**Why this exists:** The Phase 7 founder instruction scoped this session to building the AI/ML engine's models, decision logic, and API surface — it did not request an authentication layer for ai-service, and no prior phase built one (confirmed via a codebase search: `apps/ai-service/src/presentation/` has no auth dependency, middleware, or JWT-verification code anywhere). Building one now would be a substantial, unrequested scope addition, not a straightforward implementation of already-specified architecture.
**Impact:** In this monorepo's `infra/docker-compose.yml`, ai-service is only exposed on `localhost:8002` in local dev (`ports: ["8002:8000"]`) and has no separate production ingress configured — but this is a docker-compose convenience default, not a security control. Any deployment that makes ai-service network-reachable inherits this gap.
**Upgrade path:** Add a bearer-token or service-to-service auth mechanism (e.g., a shared secret header validated by FastAPI middleware, or JWT validation reusing core-api's existing `jwt_secret` infrastructure) to `src/presentation/routers/ml_router.py` and `metrics_router.py`.
**Architecture impact:** None — this is additive; no frozen design needs to change to add auth.

### A2. The frontend calls ai-service directly, not through a core-api proxy
**What:** `apps/web/lib/ai-api.ts` calls ai-service's base URL (`NEXT_PUBLIC_AI_SERVICE_BASE_URL`, defaulting to `http://localhost:8002`) directly from the browser, mirroring `lib/market-data-api.ts`'s unauthenticated `publicRequest<T>()` pattern.
**Why this exists:** `apps/core-api/src/config.py` has documented `ai_service_mode`/`ai_service_base_url` settings referencing a `MockAiServiceClient` pattern (Document 3 §7.1), but no actual `AiServiceClient` implementation, router, or proxy endpoint exists anywhere in core-api — confirmed via a codebase search before this decision was made. Building that proxy layer now would mean modifying/extending core-api, which is out of this phase's explicit "never modify Phases 1–6" boundary. Calling ai-service directly, with a complete unauthenticated REST API already built (this phase's own work), was the only option that both delivered working functionality and respected that boundary.
**Impact:** Compounds A1 — since the frontend calls ai-service directly and unauthenticated, there is no point in this request path where a user's identity or authorization is checked before an ML computation runs, beyond the `/dashboard/ai` *page route* itself being auth-gated (which only protects the UI shell, not the API).
**Upgrade path:** Build the documented `AiServiceClient`/proxy router in core-api (a follow-up phase, per `verification-report.md` §6's recommendation), then repoint `apps/web/lib/ai-api.ts` at core-api's new proxy endpoints instead of ai-service directly, gaining core-api's existing JWT auth for free.
**Architecture impact:** None currently — a future proxy-layer phase would implement, not deviate from, the already-documented `AiServiceClient` pattern.

## Category B — Disclosed Scope Decisions (introduced this phase)

### B1. `ForecastUseCase`'s per-forecast confidence is a placeholder value (0.6), not derived from held-out validation
**What:** `DecisionEngine.decide()`'s internal training flow computes real held-out RMSE/MAE per model and derives confidence from it, but the dedicated `GET /forecast/{symbol}` endpoint (backed by `ForecastUseCase`, which trains LSTM/ARIMA/Prophet fresh per request without exposing a held-out split at that call site) reports a fixed `Confidence(0.6)` for every member forecast instead.
**Why this is not a defect:** Disclosed directly in `forecast_use_case.py`'s code comment at the point of use. Deriving a genuine per-request RMSE-based confidence would require duplicating `DecisionEngine`'s private training-with-holdout flow at this second call site, which was judged not worth the duplication for a comparison-chart endpoint whose primary purpose is visualizing the 3 forecasting models' curves side-by-side, not being the authoritative confidence source (that remains `DecisionEngine`'s `Recommendation.confidence`, which the `/predict` and `/recommendation/{symbol}` endpoints do return correctly).
**Upgrade path:** Refactor the held-out-split-then-refit-on-full-series logic each model wrapper's `train()` already does internally into a reusable helper `ForecastUseCase` could call to get a genuine per-request confidence.

### B2. `PredictionRun.actual_price` backfill job is unbuilt
**What:** `PredictionRun.record_actual_price()` and the `absolute_error` property are both fully implemented and unit-tested, but nothing calls `record_actual_price()`. Every `PredictionRun` persisted via `PredictionRunRepository` has `actual_price=None` forever; the frontend's `PredictionHistory` table always renders "—" in that column.
**Why this is not a defect:** This is the same category of gap as Phase 6's `Alert` evaluation engine (B1 in `docs/phase-6/known-issues.md`) — the domain entity's lifecycle method exists and is tested, but no scheduled job calls it yet, since building that job (fetching the actual close price for each `PredictionRun`'s target date once it has passed, matching by symbol/horizon) is a distinct, separable piece of work from building the prediction pipeline itself.
**Upgrade path:** A scheduled task (mirroring `core-api`'s `market_data/tasks.py` Celery pattern) that, for each `PredictionRun` older than its earliest forecast horizon, fetches the actual OHLCV close for that date via `MarketDataRepository` and calls `record_actual_price()` + `PredictionRunRepository.save()`.

### B3. No `AdvisoryResponseEnvelope` generic wrapper type was introduced
**What:** Document 4 §9.2 describes an `AdvisoryResponseEnvelope` pattern requiring every ML-advisory response to carry a disclaimer and confidence as non-nullable fields. This phase did not introduce a separate generic Pydantic wrapper class of that name.
**Why this is not a deviation:** The underlying *requirement* — confidence, data quality, and explainability information present and non-nullable on every advisory response — is satisfied directly as required fields on `RecommendationResponse`, `ForecastResponse`'s member forecasts, and `SentimentAnalysisResponse`. This is an implementation-detail choice (fields duplicated per-DTO vs. one shared generic wrapper class), not a change to what the architecture requires the response shape to guarantee.
**Upgrade path:** If a future phase wants the generic wrapper for other reasons (e.g., a shared frontend rendering component keyed on the wrapper type), it can be introduced as a refactor without changing any field's presence or semantics.

### B4. Local-disk storage substitutes for S3 (model artifacts) and MongoDB (prediction runs)
**What:** `FileSystemModelRegistryRepository` stores `ModelVersion` metadata as JSON files under a local directory tree; `FileSystemPredictionRunRepository` stores `PredictionRun` records as append-only JSON-lines files, one per symbol. The architecture document's data-store design references S3 for artifacts and MongoDB for prediction/feature-snapshot documents.
**Why this is not a defect:** No S3-compatible object storage or MongoDB instance is configured or available in this development environment (confirmed via `apps/ai-service/.env`/`docker-compose.yml` — `infra/docker-compose.yml`'s `mongo` service exists under the `ml`/`full` profiles but was not started this session, consistent with the standing Docker-unavailable limitation, category D below). Both `ModelRegistryRepository` and `PredictionRunRepository` are domain-layer Protocols; the filesystem implementations satisfy them completely and are swappable without touching any use case or the decision engine.
**Upgrade path:** Implement `S3ModelRegistryRepository` and `MongoPredictionRunRepository` against the same Protocols once those backing services are provisioned; no other code changes needed.

### B5. FinBERT has no train/save/load — a deliberate interface difference from the other 5 models
**What:** `LstmModel`, `ArimaModel`, `ProphetModel`, `RandomForestModel`, and `XgboostModel` all expose `train()`/`save()`/`load()`. `FinBertModel` exposes only `analyze()`/`analyze_batch()` — it is used as a pretrained, off-the-shelf classifier (`ProsusAI/finbert` via HuggingFace `transformers`), never fine-tuned.
**Why this is not a defect:** Explicitly documented in `finbert_model.py`'s module docstring and matches the architecture document's sentiment-analysis design (Document 4 §10.3), which specifies using a pretrained FinBERT model, not fine-tuning one. `TrainModelUseCase.execute()` explicitly raises a `ValueError` for `family="finbert"` (verified via a passing test and mapped to HTTP 400 at the API layer) rather than silently no-op'ing or crashing unexpectedly.
**Upgrade path:** If a future phase wants a fine-tuned, domain-specific sentiment model, `FinBertModel` would need a genuinely new training pipeline (a labeled financial-sentiment dataset + a fine-tuning loop) — a substantial, separate piece of work, not a small addition to the existing wrapper.

### B6. Canary/`rollout_percentage` `ModelVersion` fields exist in the schema but the canary-promotion workflow is unexercised
**What:** `ModelVersion.rollout_percentage` (default 100) is modeled per Document 4 §10.8's frozen schema, but no code path in this phase reads or varies it — every trained version is either 100% active or fully retired, with no traffic-splitting/canary logic anywhere.
**Why this is not a defect:** `FileSystemModelRegistryRepository`'s single-instance local artifact storage has no concept of routing live inference traffic between two simultaneously-active versions of the same family — building canary promotion meaningfully requires a serving layer that can route requests, which does not exist in this phase's single-process, single-instance ai-service deployment.
**Upgrade path:** Once ai-service is deployed with multiple replicas/a load balancer capable of weighted routing, `rollout_percentage` could gate which replica set serves a given request; until then, the field is inert but harmless (present for schema fidelity, not misleading anyone into thinking canary promotion is active).

## Category C — Operating System Limitations (carried forward, re-confirmed this session)

### C1. Windows PowerShell conda-hook noise on every command
**What:** Every shell command in this environment prefixes its output with a harmless `EnvironmentNameNotFound: Could not find conda environment: proctifyAI` error and a PowerShell `Invoke-Expression` binding error.
**Impact:** Cosmetic only — re-confirmed this session across every `poetry run`/`pnpm`/`npx` invocation; never affected an actual exit code or the substance of any command's stdout used for pass/fail determination in this phase's verification.
**Resolution path:** Unchanged from Phase 1 — out of scope for this project.

## Category D — External Tooling Limitations (carried forward, re-confirmed this session)

### D1. Docker / Docker Compose not installed
**What:** Re-confirmed this session — `docker --version` still returns "not recognized."
**Impact on Phase 7:** Blocks execution of the pre-existing 55 core-api integration tests (unrelated to this phase's scope, carried forward from Phases 3–6). Also means this phase's E2E test (`ai.spec.ts`) verifies only client-side route-guard behavior, not a genuine round-trip against a running ai-service/core-api backend. The `mongo` service defined under `infra/docker-compose.yml`'s `ml`/`full` profiles (referenced by B4 above) was never started this session for the same reason.
**Resolution path:** Unchanged from Phase 1 — founder-level decision to install Docker Desktop, outside this session's scope per standing safety guardrails (a substantial system-level install).

### D2. Next.js `output: "standalone"` build fails on this Windows machine (EPERM on symlink creation)
**What:** Unchanged from Phase 1's original finding (not re-reproduced this session since Phase 6 already re-confirmed it identically) — `pnpm build` compiles successfully but fails during the standalone-output file-tracing step with `EPERM: operation not permitted, symlink ...`.
**Impact on Phase 7 verification:** The new `ai.spec.ts` E2E test, like every prior phase's E2E tests, was run against `next dev`, not a production build.
**Resolution path:** Unchanged from Phase 1 — Docker (Linux) remains the authoritative build-verification path once available.

## Accepted Technical Debt (not blockers, tracked for future phases)

- **No shared dashboard navigation shell** linking Portfolios/Watchlists/Alerts/Notifications/AI Insights/Markets — carried forward from every prior phase; `/dashboard/ai` is reachable only by direct URL or a link from wherever a future nav shell would place them.
- **`PortfolioRecommendationUseCase` accepts holdings directly as input parameters rather than calling core-api's authenticated Portfolio endpoints** — a disclosed scope boundary (documented in the use case's own module docstring) that keeps ai-service stateless and decoupled from core-api's auth machinery. The caller (a future authenticated gateway, or the presentation layer once A2's proxy layer is built) is responsible for supplying the user's actual holdings.
- **`SentimentAnalysisUseCase` and `SentimentDashboard` accept arbitrary pasted text, not a live news/social-media feed integration** — the founder's instruction named "Financial News, Company News, Reddit, Market Sentiment" as sources to analyze, but no actual news/Reddit API integration was built this phase; the FinBERT model itself is fully functional and correctly classifies whatever text it is given, but sourcing that text from live feeds is a separate, unbuilt integration.
