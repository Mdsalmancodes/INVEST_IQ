# Phase 9 — Known Issues

Issues and disclosed scope decisions identified during Phase 9 (Real-Time Market Intelligence) that remain unresolved or are deliberate, documented boundaries — not defects. Follows the same category scheme established in `docs/phase-1/known-issues.md` and used by every subsequent phase (C = environment limitations, D = external tooling limitations), plus categories for this phase's found-and-fixed defects and disclosed scope decisions.

## Category A — Defects Found and Fixed During This Phase

### A1. A test-suite hang in `test_redis_broker.py` (fixed)
**What:** Three loop-based tests (`subscribe_and_dispatch`/`psubscribe_and_dispatch`) hung indefinitely.
**Root cause:** `FakePubSub.get_message()` returned `None` with zero delay once its message queue was exhausted, turning `RedisBroker._pump()`'s poll loop into a zero-delay busy-spin. Real Redis's `get_message(timeout=...)` blocks for up to `timeout` seconds before returning `None` — the fake did not replicate this, so under some event-loop schedulers the tight spin could starve the sibling coroutine that sets the stop signal from ever being scheduled, hanging the test forever.
**Fix:** `FakePubSub.get_message()` now `await asyncio.sleep(0.001)` before returning `None` when no message is queued, forcing a genuine cooperative yield. `asyncio.wait_for(..., timeout=5.0)` was also added around all 3 affected `gather()` calls as a safety net, so any future regression of this kind fails fast with a clear `TimeoutError` instead of hanging the whole suite again.
**Verified:** the fixed file's 5 tests pass in 0.44s; the full realtime test directory passes in 1.06s; the full core-api suite passes with no hangs.

### A2. A self-introduced test-file corruption during Task 9's gap-check pass (fixed)
**What:** A file-insertion call with a stale line number landed in the middle of an existing test in `test_realtime_router.py`, splitting it into two halves with a duplicated test class inserted between them, leaving unused local variables in the truncated first half.
**Fix:** Caught immediately by ruff's unused-variable check on the very next verification pass — fixed via a full replacement of the broken region, restoring the original test intact and placing the new test class cleanly after it, then re-verified by reading the file end-to-end before re-running ruff/pytest.

## Category B — Disclosed Scope Decisions (introduced this phase)

### B1. Live sentiment refresh reuses the AI recommendation's `sentiment_score`, not a fresh `analyze_sentiment()` call
**What:** `SentimentStreamingService` does not call `AiServiceClient.analyze_sentiment()` on a schedule.
**Why:** That endpoint's request contract requires real financial-news/social-media text content, and no live news/Reddit/social-media ingestion pipeline exists anywhere in this codebase — the exact same gap Phase 7's own known-issues.md already disclosed for the on-demand `SentimentDashboard` UI, which only ever analyzes manually-pasted text. A timer-driven service has no live text feed to poll; calling `analyze_sentiment` on a schedule would mean either re-analyzing stale/empty text or fabricating placeholder text, both dishonest.
**What was built instead:** the service reuses `get_recommendation()`'s existing `sentiment_score` field — a real, already-computed value that is part of the Decision Engine's normal prediction output, not fabricated for this phase. This is the one genuinely live sentiment signal this codebase has an actual data path for.
**Upgrade path:** building a true live news/Reddit ingestion pipeline (fetching real text on a schedule and feeding it to `analyze_sentiment`) remains unbuilt and would be a substantial, separable future-phase feature.

### B2. Live Alerts implements only 4 of the 5 named trigger categories — portfolio-threshold, prediction-change, and sentiment-change conditions are not evaluated
**What:** The founder's "Live Alerts" requirement named target price, stop loss, portfolio threshold, prediction change, and sentiment change as trigger conditions. `EvaluateAlertsUseCase` implements `price_above`, `price_below`, `pct_change`, and `rsi_threshold` — the 4 condition types that already existed on `Alert.condition_type` (Phase 6, frozen). Portfolio-threshold, prediction-change, and sentiment-change are **not** implemented.
**Why:** `Alert` (Phase 6 domain entity) has no `portfolio_id` field at all today, and no existing condition type represents "a prediction changed" or "sentiment changed" in any comparable way. Inventing comparison semantics for these from scratch — what does "portfolio threshold" even compare against, and which portfolio, since an alert isn't scoped to one? — would mean designing a materially new alert sub-type, not implementing an existing one. Widening `Alert.condition_type`'s frozen `Literal`/`VALID_CONDITION_TYPES` to add 3 new literals with no defined semantics anywhere would be additive in form but not a genuine implementation of the requirement in substance.
**Upgrade path:** a future phase should design the actual comparison semantics first (e.g., does a portfolio-threshold alert need a new `portfolio_id` field on `Alert`? does a prediction-change alert compare against the previous verdict, or a confidence-score delta?) before extending the domain entity — this is genuinely new design work, not a mechanical extension.

### B3. RSI computation uses a simplified formula, not Wilder's exact smoothing, and is not shared with any ai-service indicator implementation
**What:** `evaluate_alerts_use_case.py`'s `_compute_rsi()` uses a plain-average 14-period RSI, not Wilder's exponential smoothing (the more common "true" RSI formula).
**Why:** This use case does not need Wilder's exact smoothing to serve as a meaningful overbought/oversold trigger signal, and this is a self-contained core-api computation with no dependency on ai-service's own technical-indicator code (two separate services, no shared library for this).
**Upgrade path:** if a future phase needs RSI-threshold alert precision to match a specific charting/indicator standard, replace `_compute_rsi()`'s formula — it is fully isolated in one function with dedicated tests.

### B4. Notification preferences (quiet hours, digest frequency) are not consulted before creating an alert notification
**What:** Every alert trigger creates an in-app `Notification` immediately, regardless of the user's `NotificationPreferences` row (quiet_hours_start/end, digest_frequency).
**Why:** This matches the exact scope boundary the Phase 6 `alert_models.py` module docstring itself already disclosed — the notification_preferences columns "exist and are persistable, but [the evaluation engine] does not yet consult quiet_hours/digest_frequency before creating a Notification row, since email/digest delivery itself is out of this phase's explicit scope (in-app notifications only)." Phase 9 closed the evaluation-engine gap that comment anticipated, but consulting these preference columns was never part of this phase's own scope either.
**Upgrade path:** a future phase adding email/digest delivery would be the natural point to also gate in-app notification creation on quiet hours.

### B5. `SentimentDashboard.tsx` was not wired to any real-time topic — by design, not oversight
**What:** Unlike `RecommendationCard`, `SentimentDashboard` (Phase 7, unmodified) does not subscribe to any WebSocket topic.
**Why:** Task 7's own design decision (B1 above) means live sentiment flows through the `ai:{symbol}` topic's `sentiment_score` field, already rendered inside `RecommendationCard` — not through a separate `sentiment:{symbol}` topic subscription in the UI. `SentimentDashboard` remains exactly the on-demand, manual-text-analysis tool it already was in Phase 7; wiring it to a `sentiment:` topic would have meant either duplicating the sentiment display or building a UI feature the backend design doesn't actually support (there is no live text feed to show sentiment "changing" for arbitrary pasted text).

### B6. Loading skeletons and optimistic updates were satisfied by pre-existing code, not new code
**What:** The founder's requirement list named "loading skeletons" and "optimistic updates" as frontend deliverables.
**Why disclosed explicitly:** every dashboard component's `role="status"`/`animate-pulse` loading state already existed from Phases 1–8 and was left completely untouched — Phase 9 did not need to build a new skeleton primitive. The alert-triggered toast (shown the instant a WebSocket message arrives, before any query invalidation/refetch completes) is the one genuine optimistic-update pattern added this phase; portfolio/watchlist ticks are direct cache patches, not optimistic-then-reconciled, since the WebSocket payload is itself the authoritative fresh data, not a client-side guess that might later be corrected.

## Category C — Operating System Limitations (carried forward, re-confirmed this session)

### C1. Windows PowerShell conda-hook noise on every command
**What:** Every shell command in this environment prefixes its output with a harmless `EnvironmentNameNotFound: Could not find conda environment: proctifyAI` error and a PowerShell `Invoke-Expression` binding error.
**Impact:** Cosmetic only — re-confirmed this session across every `poetry run`/`pnpm` invocation; never affected an actual exit code or the substance of any command's stdout used for pass/fail determination.
**Resolution path:** Unchanged from Phase 1 — out of scope for this project.

## Category D — External Tooling / Environment Limitations (carried forward, re-confirmed this session, plus new findings)

### D1. Docker / Docker Compose not installed — no real Redis instance, no real integration-test/E2E backend
**What:** Re-confirmed this session — no Docker daemon reachable, matching every prior phase's disclosure.
**Impact on Phase 9:** This is the single most consequential environment limitation for this phase specifically, since Phase 9's entire feature set is Redis-Pub/Sub-and-WebSocket-based. Every Redis-touching code path this phase (`RedisBroker`, every streaming service's `RedisBroker.publish()` call) either uses a test fake/double in unit tests or must tolerate connection failures gracefully in production (matching Phase 8's `RateLimitMiddleware` fail-open precedent — `RedisBroker.publish()` is explicitly fail-open, logging rather than raising). No genuine WebSocket-connect/Redis-publish/multi-instance-fan-out behavior has ever been exercised against a real Redis instance in this development environment — see `verification-report.md` §7.2 for the full list of what specifically cannot be measured here.
**Resolution path:** Unchanged from every prior phase — founder-level decision to install Docker Desktop, outside this session's scope per standing safety guardrails.

### D2. Four pre-existing E2E tests fail, unrelated to this phase (re-confirmed, not fixed)
**What:** The SAME 4 tests already disclosed in `docs/phase-8/known-issues.md` §D3 and named in `PROJECT_STATE.md`'s standing known-issues list — `auth.spec.ts`'s "login page renders and validates client-side", "register page shows password strength meter as the user types", "register page validates mismatched passwords client-side", and `markets.spec.ts`'s "typing in the search box shows a result state" — still fail identically this phase.
**Investigation performed this session:** `git status --short` confirmed neither `auth.spec.ts` nor `markets.spec.ts` appears anywhere in this session's modified-files list. Both files were re-run in complete isolation with `--workers=1`, ruling out parallel-CPU-contention as the cause — the same 4 tests fail identically every time, matching Phase 8's own conclusion that this is a genuine pre-existing environment/build condition on this constrained Windows machine, not a flake.
**Why not fixed this phase either:** doing so would require modifying `LoginForm.tsx`/`RegisterForm.tsx`/`StockSearch.tsx` or the shared validation package — all completed-phase code entirely unrelated to Phase 9's real-time scope — for a problem whose root cause was already established in Phase 8 as an environment/build artifact, not application logic.
**Resolution path:** unchanged from Phase 8's own recommendation — investigate as its own dedicated task once Docker (Linux) is available as the authoritative E2E environment.

### D3. A genuine end-to-end "WebSocket connects, a live tick arrives, the UI updates" proof is not achievable in this dev environment
**What:** `e2e/realtime.spec.ts` does not (and, in this environment, cannot) exercise a real authenticated WebSocket round-trip.
**Why:** Reaching an authenticated app state requires a real `POST /auth/login` (no backend running here per D1 above), and every live-updating dashboard widget also requires a real REST call to load its initial data before any WebSocket-driven update would even be visible in the DOM. The client-side WebSocket PROTOCOL itself (connect/reconnect/backoff/subscribe/message-routing) is fully covered at the correct tier instead — the unit level, via `useRealtimeConnection.test.ts`'s 10 tests using a purpose-built fake WebSocket — which is the appropriate place for that logic, not something E2E should duplicate even with a real backend available.
**Resolution path:** once Docker/a real backend is available, a genuine E2E live-update test becomes possible and should be added at that point, following the exact same honest-scope-then-upgrade pattern this project has used for every Category D gap since Phase 1.

## Category E — Design Notes (not defects, disclosed for completeness)

### E1. `AlertEvaluationStreamingService` re-queries OHLCV bars on every quote tick, with no dedicated caching
See `verification-report.md` §7.3 for the full writeup — a disclosed, honest scaling consideration rather than a measured problem, since no real-load environment exists here to measure its actual cost.

### E2. No ADR was required for Phase 9
Every change either wired existing domain/application logic into a new delivery mechanism, or was a straightforward additive new bounded-context module — consistent with the "no ADR needed" pattern established in Phases 6, 7, and 8 for the same reason.
