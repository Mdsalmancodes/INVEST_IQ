# Phase 7 — Implementation Summary: Hybrid AI & Machine Learning Engine

## 1. Scope Delivered

Transformed `apps/ai-service` from a Phase 1 infrastructure skeleton (health checks only) into a complete AI/ML microservice implementing exactly the 6 required model families, a Hybrid Decision Engine, SHAP explainability, a full REST API, and a frontend AI dashboard — following the same Clean Architecture layering (domain/application/infrastructure/presentation) established in `apps/core-api` across Phases 1–6. **No Phase 1–6 file was modified.** No new ADR was required (see §5 and `verification-report.md` §4 for the explicit justification).

### Domain layer (`src/domain/ml/`)

- **Value objects**: `ModelFamily` (a `Literal` of exactly `"lstm" | "arima" | "prophet" | "random_forest" | "xgboost" | "finbert"` — never a different or reduced set), `DataQuality`, `Verdict`, `SentimentLabel`, `Confidence` (self-validating `[0.0, 1.0]`), `PredictionRunId`/`ModelVersionId` (UUID wrappers), `FeatureContribution`, `ExplainabilityPayload` (max 8 contributions enforced at construction).
- **Entities**: `HorizonPoint`, `Forecast` (per-model-family forecast), `PredictionRun` (immutable ensemble record with an `actual_price` backfill hook — see known-issues.md), `SentimentScore` (with a volume-weighted `aggregate()` classmethod implementing `min(1.0, article_count / target_volume=10)`), `Recommendation` (the Decision Engine's synthesized output), `ModelVersion` (lifecycle: create/retire, canary/rollout_percentage fields modeled per the frozen schema but not exercised this phase).
- **Repository Protocols**: `MarketDataRepository`, `ModelRegistryRepository`, `PredictionRunRepository` — domain-layer interfaces, concrete implementations live in infrastructure.

### Feature engineering (`src/infrastructure/ml/features/`)

Exactly the 10 required technical indicators as pure pandas functions: SMA, EMA, RSI (Wilder's method), MACD, Bollinger Bands, ATR, VWAP, OBV, ROC, ADX. `FeatureEngineer` orchestrates all 10 into a `FeatureMatrix`, omitting (not truncating) any indicator below its minimum-window requirement, per the architecture doc's degraded-ensemble design. Handles missing values (ffill+bfill) and per-column scaling (StandardScaler, fit on non-NaN values only).

### The 6 required models (`src/infrastructure/ml/models/`)

| Model | Library | Minimum history | Role |
|---|---|---|---|
| LSTM | PyTorch (`nn.LSTM`) | 90 days (60-day lookback window) | Next-day/7-day/30-day price forecast |
| ARIMA | statsmodels (`order=(5,1,0)`) | 20 days | Price forecast, trend/seasonality |
| Prophet | Facebook Prophet (real `prophet.Prophet()`) | 30 days | Long-term forecast |
| Random Forest | scikit-learn (`RandomForestClassifier`) | 20 days | Movement classification + feature importance |
| XGBoost | XGBoost (`XGBClassifier`) | 20 days | Movement classification + Buy/Sell probability |
| FinBERT | HuggingFace Transformers (`ProsusAI/finbert`) | N/A (pretrained) | Sentiment analysis (positive/negative/neutral + confidence) |

All 6 are genuinely functional in this environment — real training, real inference, no models faked or stubbed. Prophet in particular required correcting an initial, incorrect belief during this session that CmdStan was unavailable on Windows; a working CmdStan install was found to already exist, and all 10 real Prophet tests pass with genuine Stan optimizer runs. FinBERT is deliberately the one exception to the train/save/load interface the other 5 share — it is used pretrained, not fine-tuned, per the architecture doc's sentiment-analysis design.

### Hybrid Decision Engine (`src/application/ml/decision_engine.py`)

Combines all 6 models via weighted voting with confidence-adjusted weights (`random_forest=0.22, xgboost=0.22, lstm=0.20, prophet=0.14, arima=0.12, finbert=0.10`, summing to 1.0). Gracefully **excludes** (never fails on) any model below its own minimum-history threshold, Prophet if unavailable, FinBERT if no news text is supplied, or a tree-based classifier if the actual 80% training split it would use contains only one class (a genuine edge case discovered this session — see §3). Overall confidence combines average member confidence with an agreement factor (low signal variance across members → higher confidence). Produces a `Recommendation` (BUY/SELL/HOLD + confidence % + price forecast + market sentiment score) plus a portfolio-level aggregation and per-instrument SHAP explainability. This weighted-voting-across-all-6-models design is a superset of the architecture document's narrower rules+scoring synthesis — built per the founder's explicit Phase 7 instruction, not a silent deviation (see §5).

### SHAP Explainability (`src/infrastructure/ml/explainability/shap_explainer.py`)

`ShapExplainerService` (matching the architecture doc's exact specified path and class name) wraps `shap.TreeExplainer` for the Random Forest and XGBoost members specifically (SHAP's natural fit for tree-based models). Produces real per-instance SHAP contributions — not a simplified "top feature-importance entry" placeholder — with a documented, narrow fallback to the simpler approach only if SHAP explanation genuinely raises for any reason.

### Application layer use cases (`src/application/ml/`)

`PredictUseCase` (backs both "Predict" and "Buy/Sell/Hold Recommendation" — the same `Recommendation.verdict` computation, per the founder's instruction that these are the same answer), `ForecastUseCase` (LSTM/ARIMA/Prophet only, for the dedicated forecast-comparison endpoint), `SentimentAnalysisUseCase`, `PortfolioRecommendationUseCase` (accepts holdings directly rather than calling core-api's authenticated portfolio endpoints — a disclosed scope boundary, see known-issues.md), `PredictionHistoryUseCase`, `ModelStatusUseCase`, `TrainModelUseCase`/`RetrainModelUseCase`.

### Infrastructure layer (`src/infrastructure/{http,persistence}/`)

`HttpMarketDataRepository` calls core-api's existing public `GET /api/v1/instruments/{symbol}/bars` endpoint via httpx — **never duplicates the `ohlcv_bars` table or opens a direct database connection**, per the founder's explicit "reuse Market Data module" instruction. `FileSystemModelRegistryRepository` and `FileSystemPredictionRunRepository` persist model versions and prediction runs to local disk (JSON per version, append-only JSON-lines per symbol) — disclosed substitutes for S3/MongoDB respectively (see known-issues.md).

### Presentation layer (`src/presentation/`)

Full REST API under `/api/v1/ml`: `POST /train`, `POST /retrain`, `POST /predict`, `GET /recommendation/{symbol}` (buy/sell/hold), `GET /forecast/{symbol}`, `POST /sentiment`, `POST /portfolio-recommendation`, `GET /history/{symbol}`, `GET /models/status`, plus `GET /metrics` — every founder-required endpoint. Pydantic DTOs mirror every domain concept; `raise_ml_exception_as_http()` maps `MlDomainError` subtypes to HTTP status codes; FastAPI `Depends()`-based DI wiring (no custom container), matching core-api's exact conventions. `/health`/`/ready` (built Phase 1) unchanged.

### Frontend (`apps/web/features/ai/`)

`AIDashboard` (top-level composition) → `RecommendationCard` (verdict + confidence + price forecasts + sentiment + SHAP panel), `ForecastChart` (lightweight-charts multi-line LSTM/ARIMA/Prophet comparison), `PredictionChart` (all-6-models weighted-vote visualization), `SentimentDashboard` (FinBERT text analysis), `PredictionHistory`, `ModelStatus`, `ConfidenceIndicator`, `ShapExplanationPanel`. Backed by `lib/ai-api.ts` (a new, disclosed unauthenticated client calling ai-service directly — see known-issues.md) and `features/ai/hooks/useAi.ts` (TanStack Query). Route: `/dashboard/ai`, auth-guarded consistently with the rest of `/dashboard/*`.

## 2. Test Evidence

| Suite | Count | Result |
|---|---|---|
| ai-service unit — domain (`entities.py`) | 23 | all passing |
| ai-service unit — feature engineering (indicators + engineer) | 27 | all passing |
| ai-service unit — LSTM model | 7 | all passing (real torch training) |
| ai-service unit — ARIMA model | 10 | all passing (real statsmodels fits) |
| ai-service unit — Prophet model | 10 | all passing (real CmdStan/Stan fits) |
| ai-service unit — Random Forest model | 11 | all passing (real sklearn training) |
| ai-service unit — XGBoost model | 13 | all passing (real xgboost training) |
| ai-service unit — FinBERT model | 8 | all passing (real ProsusAI/finbert inference) |
| ai-service unit — SHAP explainability | 6 | all passing (real trained tree models) |
| ai-service unit — Decision Engine | 10 | all passing (real full 6-model pipeline) |
| ai-service unit — application-layer use cases (7 files) | 37 | all passing |
| ai-service unit — HTTP market data repository | 4 | all passing (real httpx roundtrip via MockTransport) |
| ai-service unit — model registry repository | 7 | all passing |
| ai-service unit — prediction run repository | 7 | all passing |
| ai-service unit — presentation layer (2 router test files) | 22 | all passing (real FastAPI TestClient, real model execution) |
| **ai-service total** | **193** | **all passing** |
| core-api — regression check (all pre-existing suites) | 401 | all passing, zero regressions (55 deselected, Docker unavailable) |
| apps/web unit — new AI components (9 files) | 29 | all passing |
| apps/web unit — pre-existing, regression check | 89 | all passing, zero regressions |
| **apps/web unit total** | **118** | **all passing** |
| apps/web E2E — new `/dashboard/ai` route-guard spec | 1 | passing |
| apps/web E2E — pre-existing, regression check | 20 | all passing, zero regressions |
| **apps/web E2E total** | **21** | **all passing** |

**Grand total this phase's verification scope: 193 (ai-service) + 401 (core-api regression) + 118 (web unit) + 21 (web E2E, run separately from the unit count) = 733 individual test executions** — see `verification-report.md` for the exact reproduced command output backing each figure.

## 3. Real Defects Found and Fixed (via execution, not inspection)

| # | Defect/Gap | Category | Fix |
|---|---|---|---|
| 1 | Initial belief that Prophet was blocked by missing CmdStan/`mingw32-make` on Windows | A (investigation correction) | Re-verified with a direct real-fit probe; a working CmdStan install was already present. Corrected the record — no Prophet limitation exists in this environment. |
| 2 | RSI's zero-division edge case (`avg_loss == 0`) produced `inf`/`NaN` instead of the correct RSI=100/50 boundary values | A (test-caught) | Explicit `.mask()` handling for the "all gains, zero losses" (RSI=100) and "flat prices" (RSI=50) cases |
| 3 | `pd.NA` used throughout `indicators.py` broke float `.astype()`/division in this pandas version | A (runtime-caught) | Replaced all `pd.NA` with `np.nan` |
| 4 | `LstmModel.save()`/`.load()` didn't persist `hidden_size`/`num_layers`, causing a `state_dict` shape-mismatch `RuntimeError` when loading a non-default architecture | A (test-caught) | Persisted both hyperparameters in the checkpoint dict; reconstruct the correct architecture before `load_state_dict` |
| 5 | `ShapExplainerService`'s `_HasUnderlyingTreeModel` Protocol used an invariant plain attribute, failing structural typing against `RandomForestModel`/`XgboostModel`'s differently-typed concrete `_model` attributes | A (mypy-caught) | Switched to a covariant `@property` (mypy checks properties covariantly, attributes invariantly) |
| 6 | Both new repository files' JSON (de)serialization helpers typed dict params as `dict[str, object]`, causing mypy `attr-defined`/`call-overload` errors on key access | A (mypy-caught) | Used `dict[str, Any]` throughout, consistent with the codebase's established Any-for-dynamic-boundary convention |
| 7 | Synthetic OHLCV test fixtures initially used an identical `bar_time` for every bar, breaking Prophet's Stan optimizer (NaN from a zero-variance date regressor) | A (test-caught, real-library interaction) | Ascending, genuinely distinct dates in the shared `_fixtures.py` helper |
| 8 | `FakeModelRegistryRepository.save()` test double appended every call instead of upserting by id, producing a false-positive duplicate-version count once `ModelVersion.retire()` (a mutation) was exercised | A (test-caught) | Fixed to upsert by id, matching real repository semantics |
| 9 | A strong uninterrupted price trend in synthetic test data produced single-class classification labels, which sklearn/xgboost classifiers cannot fit (`ValueError`) — a genuine ensemble-design edge case, not just a test artifact | A (discovered via real training, addressed in production code) | Added `_has_both_classes()` to `DecisionEngine`, checking the actual 80% internal train split each tree model uses; gracefully excludes RF/XGBoost from the ensemble (added to `excluded_models`) rather than crashing |
| 10 | `POST /train`/`POST /retrain` endpoints initially only caught `MlDomainError`/`MarketDataUnavailableError`, not the bare `ValueError` `TrainModelUseCase` raises for `family="finbert"` (not trainable) | A (test-caught) | Added an explicit `except ValueError` clause mapping to HTTP 400 in both endpoints |
| 11 | `test_returns_the_most_recently_trained_active_version` was genuinely flaky — two back-to-back `ModelVersion.create()` calls can land within the same Windows clock-tick, making `get_active_for_family()`'s tie-break non-deterministic | A (test-design bug, not production-logic — real training runs are always seconds/minutes apart) | Added an explicit `trained_at` override to the test helper; passed clearly-distinct timestamps |
| 12 | `SentimentDashboard.test.tsx`'s `getByText("positive")` assertion was ambiguous (both the aggregate label and the single per-item score render the literal text "positive" in the fixture) | A (test-caught, same category as Phase 6's `CreateAlertDialog.test.tsx` fix) | Scoped to `getAllByText("positive").length > 0` — a real structural assertion instead of a weakened one |

No defects were found in any pre-existing Phase 1–6 file — none was modified, and the full core-api/ai-service-boundary regression check (§2) confirms zero side effects.

## 4. Disclosed Limitations

See `known-issues.md` for the complete, detailed list. In summary: ai-service's REST API is entirely unauthenticated (a disclosed, phase-scoped security note); the frontend calls ai-service directly rather than through an unbuilt core-api proxy; `ForecastUseCase` uses a placeholder confidence value; `PredictionRun.actual_price` backfill is unbuilt; no separate `AdvisoryResponseEnvelope` wrapper type was introduced (its required fields are satisfied directly on each response DTO); local-disk storage substitutes for S3/MongoDB; FinBERT has no train/save/load; canary/rollout fields exist in the schema but are unexercised.

## 5. Architecture Fidelity

- Clean Architecture dependency rule maintained: domain has zero framework/library imports (no numpy/pandas/torch leak into `domain/ml/`); infrastructure implements domain-defined Protocols; application depends on Protocols and concrete model wrapper instances (there is no separate "ModelRepository per family" abstraction in the frozen architecture — model wrappers are constructor-injected directly into `DecisionEngine`, matching how the architecture doc describes the ensemble); presentation never talks to infrastructure directly.
- Exactly the 6 required model families were implemented — never substituted, removed, or added to.
- Market Data was reused via HTTP, never duplicated — confirmed no direct Postgres connection exists anywhere in ai-service, and `ohlcv_bars` was never re-modeled.
- The Decision Engine's weighted-voting-across-all-6-models design is a **superset** of the architecture document's narrower rules+scoring synthesis (Document 4 §10.4) — built per the founder's explicit Phase 7 instruction to combine all 6 models via weighted voting, not a silent deviation from the frozen design.
- **No ADR was drafted or required.** Every architectural choice this phase either directly implemented what the architecture document already specified (the minimum-history table, the partialEnsemble degraded pattern, SHAP's exact class name/path, the `ModelVersion` lifecycle schema), or was an explicit extension the founder's own instruction called for (weighted voting across all 6 models). No frozen decision was changed or reversed.
