# Phase 9 — Verification Report

## 1. Backend Verification (core-api)

Commands run from `apps/core-api`:

```
poetry run ruff check .
poetry run mypy src
poetry run pytest -q
```

**Result:** ruff — all checks passed (190 source files). mypy — success, no issues found (190 source files). pytest — **554 passed, 55 deselected** (Docker-unavailable integration tests, carried forward from every prior phase).

**Baseline comparison:** 459 tests passing at the end of Phase 8 → 554 at the end of Phase 9 (**+95 net new tests**), zero regressions.

New tests this phase, by task:
- Task 2 (WebSocket infrastructure): 31 tests — `test_connection_manager.py` (12), `test_redis_broker.py` (5), `test_subscription_registry.py` (5), `test_ws_auth.py` (4), `test_realtime_router.py` (5).
- Task 3 (live stock data): 7 tests — `test_connection_manager.py` (+2), `test_market_data_streaming_service.py` (5, new).
- Task 4 (live watchlist): 8 tests — `test_connection_manager.py` (+4), `test_watchlist_streaming_service.py` (4, new).
- Task 5 (live portfolio): 7 tests — `test_sector_allocation.py` (4, new), `test_portfolio_streaming_service.py` (3, new).
- Task 6 (live AI): 5 tests — `test_ai_prediction_streaming_service.py` (new).
- Task 7 (live sentiment): 5 tests — `test_sentiment_streaming_service.py` (new).
- Task 8 (live alerts / Alert Evaluation Engine): 16 tests — `test_evaluate_alerts_use_case.py` (12, new), `test_alert_evaluation_streaming_service.py` (4, new).
- Task 9 (gap-check pass): 16 tests — `test_realtime_service.py` (12, new), `test_realtime_router.py` (+4).

## 2. Backend Verification (ai-service)

Commands run from `apps/ai-service`:

```
poetry run ruff check .
poetry run mypy src
poetry run pytest -q
```

**Result:** ruff — all checks passed (53 source files). mypy — success, no issues found (53 source files). pytest — **202 passed** (912 warnings, all pre-existing third-party `shap` library deprecation noise, unrelated to any codebase change).

**Baseline comparison:** 202 tests passing at the end of Phase 8 → 202 at the end of Phase 9 (**+0 net new tests**) — ai-service was not touched at all this phase; Live AI/Live Sentiment go through the existing Phase 8 `AiServiceClient` proxy with zero ai-service-side code changes required, as designed.

## 3. Frontend Verification (apps/web)

Commands run from `apps/web` (via `pnpm --filter @investiq/web ...`):

```
pnpm typecheck
pnpm lint
pnpm test:unit
pnpm exec playwright test
```

**Result:**
- `typecheck` — clean, zero errors.
- `lint` — clean, zero errors/warnings.
- `test:unit` — **181 passed** (41 test files) confirmed in isolation; one full-suite run showed 180/181 due to a pre-existing CPU-contention-sensitive flake in `RegisterForm.test.tsx` (a Phase 2 file never touched this phase — passes 4/4 reliably in isolation, confirmed repeatedly).
- `playwright test` (full suite, 10 spec files) — **21 passed**, 4 failed (see §6 below — pre-existing, not a Phase 9 regression).

**Baseline comparison:**
- Unit tests: 156 (Phase 8 baseline) → 181 (**+25 net new tests**), zero regressions.
- E2E specs: 18 passing (Phase 8 baseline) → 21 passing (+3 new spec), plus the same 4 pre-existing failures carried forward unchanged.

New unit test files/additions this phase, by task:
- Task 11 (WebSocket client hook): 10 tests — `features/realtime/hooks/useRealtimeConnection.test.ts` (new).
- Task 13 (primitives + wiring gap-check): 15 tests — `features/realtime/components/AnimatedNumber.test.tsx` (4, new), `Toast.test.tsx` (5, new), `ConnectionStatusBadge.test.tsx` (4, new), `LiveQuote.test.tsx` (+1), `NotificationsList.test.tsx` (+1).

New E2E spec: `e2e/realtime.spec.ts` (3 tests).

## 4. Combined Monorepo Totals

| Suite | Phase 8 baseline | Phase 9 final | Net new |
|---|---|---|---|
| core-api unit/integration | 459 passing (+55 deselected) | 554 passing (+55 deselected) | +95 |
| ai-service unit | 202 passing | 202 passing | +0 |
| apps/web unit | 156 passing | 181 passing | +25 |
| apps/web E2E | 18 passing (+4 pre-existing) | 21 passing (+4 pre-existing, unchanged) | +3 |
| packages/ui unit | 4 passing | 4 passing | +0 |
| **Grand total (passing)** | **839** | **962** | **+123** |

## 5. Zero Regressions to Phases 1–8 — How Verified

Every full-suite command above was re-run fresh at multiple checkpoints across this phase (Task 10 for backend, Task 14 for frontend), not assumed from "no files touched." `git status --short` was checked before attributing any test failure to a pre-existing/unrelated cause, confirming the specific files involved (`RegisterForm.test.tsx`, `auth.spec.ts`, `markets.spec.ts`) were never modified this session.

The one genuine self-introduced bug this phase (a `write` tool insertion landing mid-test in `test_realtime_router.py`, Task 9) was caught immediately by ruff's unused-variable check on the very next verification pass, before being marked complete — not discovered later.

## 6. Pre-Existing E2E Failures — Not a Phase 9 Regression

4 of the 25 total E2E tests fail consistently, both before and after every Phase 9 change — the same 4 tests already disclosed in `docs/phase-8/known-issues.md` and `PROJECT_STATE.md`'s standing known-issues list (item 6):
- `auth.spec.ts` — "login page renders and validates client-side", "register page shows password strength meter as the user types", "register page validates mismatched passwords client-side"
- `markets.spec.ts` — "typing in the search box shows a result state (error, since no backend is running)"

Re-confirmed this phase via `git status --short` (neither file appears in this session's modified-files list) and via re-running both files in complete isolation with `--workers=1` (ruling out parallel-CPU-contention as the cause — the same 4 tests fail identically every time, a genuine pre-existing condition, not a flake). Out of scope to fix per the "do not modify completed phases" rule, since these are Phase 2/4 specs.

## 7. Performance Verification

No real Redis instance or production-scale load exists in this development environment (the same standing Category D limitation disclosed in every prior phase's known-issues — Docker unavailable). Every Redis-touching test in this phase uses a fake broker/pub-sub. This section is therefore a **design-decision-based analysis**, not a load-test measurement, matching exactly how Phase 8's own rate-limiter verification handled the identical constraint.

### 7.1 Design decisions that bound cost

- **Staggered poll intervals by actual computational cost, not uniform**: market data 5s (a single quote lookup), watchlist/portfolio 10s (N-item enrichment or a full holdings recalculation), AI/sentiment 30s (a 5-model ensemble prediction is far more expensive than either). A uniform interval would have either made the ticker feel sluggish or made the AI pipeline recompute far more often than useful.
- **Subscription-gated work everywhere**: `ConnectionManager.all_subscribed_topics()`/`user_ids_subscribed_to()` mean every one of the 6 poll-driven streaming services only computes and publishes for symbols or users a connected client is actually subscribed to right now — never a fixed universe of "all known symbols" or "all users." An idle server with zero connected clients does zero work beyond the poll loops' own no-op iteration.
- **Redis Pub/Sub fan-out, not Streams or per-client polling**: a `publish()` call is O(1) regardless of how many core-api instances or connected clients are subscribed; horizontal scaling requires zero cross-instance coordination (every instance independently subscribes to the same channels).
- **`AlertEvaluationStreamingService` piggybacks on existing publishes** rather than running a 7th independent poll loop — it subscribes to `realtime:quote:*`, so alert evaluation happens exactly once per quote tick that `MarketDataStreamingService` was already going to publish, with zero additional polling overhead.
- **Client-side: one shared WebSocket connection per browser tab**, not one per widget — connection count is bounded by open tabs, not by how many live-updating components are mounted on a page.
- **Client-side: ref-counted subscribe/unsubscribe** — if 3 components on the same page all subscribe to `quote:AAPL`, exactly one `subscribe` message is sent to the server (on the first component to mount) and exactly one `unsubscribe` message (when the last one unmounts), not 3 of each.
- **`MarketDataCache` (Phase 4, 30s TTL, unmodified) naturally deduplicates** redundant quote lookups across the market-data streaming, watchlist streaming, and alert-evaluation code paths that all ultimately call `GetCurrentPriceUseCase` within the same ~30-second window — most of those calls are cache hits, not fresh provider round-trips.
- **Client-side rendering (`AnimatedNumber`, toasts) is pure browser-side work** — zero additional server cost per animation frame.

### 7.2 What cannot be measured in this environment

- Real Redis Pub/Sub publish/dispatch latency under concurrent load.
- Real concurrent-WebSocket-connection behavior at any meaningful scale (tested only with a handful of connections in unit tests via fakes).
- Real network bandwidth consumption per connection per poll cycle.
- Real multi-instance horizontal-scaling behavior (the fan-out design is architecturally sound and unit-tested for correctness of the translation/dispatch logic, but has never run against two real core-api processes sharing a real Redis instance).

### 7.3 A disclosed, honest scaling concern (not a bug)

`AlertEvaluationStreamingService.handle_quote()` re-queries the last 30 OHLCV bars from Postgres on **every** quote tick for **every** symbol that has at least one active alert, to support RSI computation — there is no caching of this specific query. For a symbol with many active alerts across many users, this is still only **one** query per quote tick (not one per alert), but it is a query this service runs independently of `MarketDataStreamingService`'s own tick, meaning the same symbol's bars could be queried by two different services within the same few seconds. This was a deliberate simplicity-over-premature-optimization choice (this dev environment has no realistic load to profile against), disclosed here rather than either silently left unmentioned or "fixed" without any way to verify the fix actually helps.

## 8. Manual/Exploratory Verification

- Confirmed via direct code reading (not assumption) that every Phase 9 streaming service's payload field names match exactly what the corresponding frontend TypeScript interface expects, before writing each dashboard component's cache-patch logic (e.g. `market_data_streaming_service.py`'s `_tick_to_payload` vs. `CurrentPriceResponse`; `portfolio_streaming_service.py`'s `_summary_to_payload` vs. `PortfolioSummaryResponse`).
- Confirmed `main.py`'s lifespan starts all 7 background services in the documented order and stops them in the exact reverse order on shutdown, by reading the final file end-to-end rather than trusting each individual additive edit in isolation.
