# Phase 9 — Real-Time Market Intelligence — Implementation Summary

Phase 9 transforms INVEST IQ from a request/response application into a real-time platform: live stock prices, live watchlist/portfolio updates, live AI predictions and sentiment, and instant alert notifications, all delivered over a single shared WebSocket connection per browser tab, backed by Redis Pub/Sub for horizontal scalability. This document summarizes what was built, task by task, and the design decisions behind it.

## 1. Investigation (Task 1)

Confirmed via direct codebase inspection before writing any code:

- **No WebSocket infrastructure existed anywhere** in the monorepo — zero WS routers, zero connection tracking, zero Pub/Sub consumers. Phase 6/7/8's own known-issues docs had already disclosed this as deferred to a later phase.
- **Redis architecture** (already built in core-api's `RedisClients`): three separate instances — `redis-cache` (quotes, Phase 4), `redis-broker` (Celery + explicitly documented "Alert Streams" — the architecturally-designated Pub/Sub channel), `redis-session` (rate-limit/session, Phase 8). Phase 9's Pub/Sub reuses `redis-broker` — no new Redis instance was created.
- **The Alert Evaluation Engine had never been built.** `Alert.can_trigger_now()`/`trigger()` (Phase 6 domain methods) existed and were fully unit-tested, but nothing anywhere called them — this was the standing Phase 6/7/8 known-issue that Phase 9 was required to close.
- `MarketDataCache` (30s TTL) and the Celery `sync_instrument_bars` task were the only existing market-data-freshness mechanisms — no continuous/streaming feed exists (yfinance is polling-only, a disclosed Phase 4 limitation carried forward).
- `PortfolioCalculationService` (Phase 3) computed everything needed for live portfolio updates except sector allocation — a new aggregation, buildable from the existing `Instrument.sector` field without new schema.
- `WatchlistEnrichmentService` (Phase 5) already computed per-item live quotes on each HTTP call — reusable as-is for live watchlist streaming.
- The frontend had zero WebSocket client code, no toast library, but already had `motion` (framer-motion) as a dependency, usable for animations without a new dependency.

## 2. Backend WebSocket Infrastructure (Task 2)

New bounded-context module `apps/core-api/src/infrastructure/realtime/`:

- **`ConnectionManager`** — tracks WebSocket connections per user (supports multiple simultaneous connections/tabs per user), each connection paired with its own `SubscriptionRegistry`. Provides `connect()`/`disconnect()`/`send_to_user()`/`broadcast()` (both topic-filterable), plus query helpers (`all_subscribed_topics()`, `user_ids_subscribed_to(prefix)`) that every streaming service uses to avoid computing/publishing for anything nobody is watching.
- **`SubscriptionRegistry`** — a pure per-connection set of subscribed topic strings.
- **`RedisBroker`** — a thin Pub/Sub wrapper over the existing `redis-broker` instance. `publish()` is fail-open (logs, never raises, matching Phase 8's `RateLimitMiddleware` precedent). Supports exact-channel (`subscribe_and_dispatch`) and glob-pattern (`psubscribe_and_dispatch`) subscriptions.
- **`channels.py`** — centralized Redis channel-naming functions, used by every publisher instead of hand-written strings.
- **`ws_auth.py`** — `authenticate_websocket()` reuses the existing `JwtProvider`/`TokenBlacklist` verification logic via a query-parameter token (browsers cannot set custom headers on a WebSocket handshake).
- **`RealtimeService`** — the single process-wide bridge from Redis Pub/Sub to `ConnectionManager` delivery, translating internal channel names to the public WS topic contract.
- **`realtime_router.py`** — the single endpoint, `WS /api/v1/realtime/ws?token=<access_token>`. Sends a `{"type":"connected"}` frame on success, runs a 15-second heartbeat task concurrently with the message-receive loop, and handles `ping`/`subscribe`/`unsubscribe` client actions.

**Horizontal scalability**: N core-api instances each run their own `ConnectionManager` (in-memory) and `RealtimeService` (subscribed to the same Redis channels) — a publish on any instance reaches every instance's own locally-connected clients without cross-instance coordination.

## 3. Live Stock Data Streaming (Task 3)

`MarketDataStreamingService` — an asyncio background loop (default 5s interval, the shortest of any Phase 9 service, disclosed as a polling interval since no genuinely continuous provider exists in this dev environment). Each tick publishes market status via the existing `GetMarketStatusUseCase`, and for every symbol a connected client is actually subscribed to (`quote:SYMBOL` topics — never a fixed universe), calls the existing `GetCurrentPriceUseCase` plus `OhlcvBarRepository` for OHLC/volume and publishes a quote tick.

## 4. Live Watchlist Updates (Task 4)

`WatchlistStreamingService` (10s interval) reuses the existing `WatchlistEnrichmentService` unmodified — its only job is deciding when to re-run it and where to publish, for every user with an open "watchlist" subscription.

## 5. Live Portfolio Updates (Task 5)

`PortfolioStreamingService` (10s interval) reuses `PortfolioCalculationService` unmodified, plus a new `compute_sector_allocation()` helper layered on top (grouping already-computed holding values by `Instrument.sector`, with an explicit "Unknown" bucket for holdings with no sector data) — satisfying the sector-allocation/distribution requirement without touching the frozen Phase 3 calculation service.

## 6. Live AI Prediction Pipeline (Task 6)

`AiPredictionStreamingService` (30s interval — the longest so far, since a full 5-model ensemble is expensive) calls the existing `AiServiceClient.get_recommendation()` for every subscribed symbol — the same sanctioned proxy client the HTTP-triggered `ai_proxy_router.py` already uses exclusively, preserving the Phase 8 "AI Service must never be directly exposed" boundary. A non-200 response (e.g. insufficient history) is skipped, not treated as an error.

## 7. Live Sentiment Analysis Refresh (Task 7)

`SentimentStreamingService` (30s interval) reuses the same `get_recommendation()` call, extracting its existing `sentiment_score` field rather than calling `analyze_sentiment()` (which requires real news/social-media text this codebase has no live ingestion pipeline for — see known-issues.md). This is the one genuinely live sentiment signal the codebase has an actual data path for.

## 8. Live Alerts — the Alert Evaluation Engine (Task 8)

The most architecturally significant task — `EvaluateAlertsUseCase` is the first-ever caller of `Alert.can_trigger_now()`/`trigger()`. Given a symbol's current price (and recent closes for RSI), it evaluates every active alert on that instrument via the existing `AlertRepository.list_active_for_instrument`, defines condition semantics for `price_above`/`price_below`/`pct_change`/`rsi_threshold`, and on a match, persists a `Notification` via the existing Phase 6 entity/repository.

`AlertEvaluationStreamingService` triggers this by independently subscribing to `realtime:quote:*` via Redis Pub/Sub (mirroring `RealtimeService`'s own pattern) rather than hooking into `MarketDataStreamingService` — zero modification to that already-verified class, and horizontally-scalability-correct for free (evaluates correctly regardless of which instance published the quote). Triggered notifications are published to `channels.alert_channel(user_id)`.

Portfolio-threshold, prediction-change, and sentiment-change alert conditions were **not** implemented — see known-issues.md.

## 9. Backend Test Gap-Check (Task 9)

A dedicated pass confirmed two real gaps and closed them: `RealtimeService`'s own channel-to-topic translation and dispatch routing had no direct tests (only indirect, through other services), and `realtime_router.py`'s WS endpoint lacked auth-failure (invalid/expired/blacklisted token) and heartbeat-delivery tests.

## 10. Full Backend Verification (Task 10)

core-api: ruff/mypy clean, **554 tests passing / 55 deselected** (+95 from Phase 8's 459 baseline). ai-service: ruff/mypy clean, **202 tests passing**, unchanged — confirming zero ai-service code changes were needed for Live AI/Live Sentiment, since both went through the existing Phase 8 proxy client.

## 11. Frontend WebSocket Client Infrastructure (Task 11)

`useRealtimeConnection()` — a single shared WebSocket connection per browser tab (not one per widget), reading the access token from the existing `useAuthStore`. Exposes `connectionState` (`connecting`/`connected`/`reconnecting`/`offline`) and a ref-counted `subscribe(topic, listener)` API. Auto-reconnects with exponential backoff (1s → 30s cap), re-subscribing to every previously-registered topic on reconnect (the server documents this as always a safe no-op). Sends its own `ping` every 20s as an additional proactive dead-connection detector alongside the server's 15s heartbeat.

## 12. Live-Updating Dashboards (Task 12)

Two new client-side primitives (`apps/web/features/realtime/components/`, placed there rather than `packages/ui` since that package has no `motion` dependency): `AnimatedNumber` (smooth numeric transitions) and an in-house `Toast`/`useToastStore`/`ToastContainer` (no toast library exists anywhere in this monorepo, matching the codebase's established "no new dependency for a narrow need" pattern). `ConnectionStatusBadge` surfaces `connectionState` — silent while connected/offline, a visible pill only while connecting/reconnecting. Both new UI primitives are mounted globally in `app/providers.tsx`.

Six existing dashboard components were wired additively — each subscribes to its topic in a `useEffect` and patches or invalidates the exact TanStack Query cache key its own existing hook already reads from, so every component works identically with the WebSocket offline, just without the live updates:

| Component | Topic | Behavior |
|---|---|---|
| `LiveQuote` | `quote:{symbol}` | Patches the quote cache; price renders via `AnimatedNumber` |
| `WatchlistTable` | `watchlist` | Merges item-level quote fields into the cache, preserving non-quote fields |
| `PortfolioSummaryCards` | `portfolio:{portfolioId}` | Replaces summary fields wholesale, preserving holdings; new Sector Allocation card |
| `NotificationsList` | `alert` | Shows an instant toast + invalidates the list |
| `AlertsList` | `alert` | Invalidates the list so the Active/Inactive badge stays in sync |
| `RecommendationCard` | `ai:{symbol}` | Replaces the recommendation cache wholesale (identical shape to the REST response) |

Loading skeletons were **not** newly built — Phase 1–8's existing `role="status"`/`animate-pulse` loading states already existed in every component and were left untouched.

## 13. Frontend Tests (Task 13)

Dedicated unit tests were written for all 3 new primitives (previously zero direct coverage), and two dashboard components (`LiveQuote`, `NotificationsList`) were extended with tests that capture the mocked `subscribe()` callback and invoke it directly, proving the actual cache-patch/toast code paths work — not just that the component renders with a mocked hook. A new `e2e/realtime.spec.ts` follows the exact same honest-scope pattern as every existing spec (no real backend in this dev environment) — verifying route protection was not broken and that the new global indicators are safe no-ops while logged out.

## 14. Full Frontend Verification (Task 14)

apps/web: typecheck/lint clean, **181 unit tests passing**, 21/25 E2E passing (4 pre-existing, unrelated failures — see known-issues.md). packages/ui: unchanged baseline, 4 tests passing.

## 15–16. Performance and Documentation

See `verification-report.md` (performance analysis) and `known-issues.md` (all disclosed gaps) for the remaining two tasks.

## Cumulative Test Counts

| Suite | Phase 8 baseline | Phase 9 final | Net new |
|---|---|---|---|
| core-api | 459 passing (+55 deselected) | 554 passing (+55 deselected) | +95 |
| ai-service | 202 passing | 202 passing | +0 (untouched) |
| apps/web unit | 156 passing | 181 passing | +25 |
| apps/web E2E | 18 passing (+4 pre-existing failures) | 21 passing (+4 pre-existing failures) | +3 |
| packages/ui | 4 passing | 4 passing | +0 (untouched) |
| **Grand total (passing)** | **835 (est.)** | **962** | **+127** |

No ADR was required for Phase 9 — every change either wired existing domain/application logic into a new delivery mechanism (WebSocket push alongside REST), or was a straightforward additive new bounded-context module. Phases 1–8 were not modified except via strictly additive extensions (new imports, new lifespan entries, new optional fields).
