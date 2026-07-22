# Phase 4 Verification Report — Market Data Foundation

**Status:** Complete and verified. **Recommendation: approve Phase 4** (see §6). No blocking follow-up conditions (unlike Phase 3, both prior ADRs are now Accepted).

## 1. Scope Delivered

Backend (`apps/core-api`, Clean Architecture — domain/application/infrastructure/presentation):
- **Domain layer** (`src/domain/market_data/`): `Instrument`, `OhlcvBar` (OHLC-consistency validation, `with_adjusted_close()`), `CorporateAction` (split/dividend/spinoff validation, `backward_adjustment_factor()`); `Price`/`Interval`/`CorporateActionId` value objects (`InstrumentId` reused from `domain.portfolio`, not duplicated); 8 domain exceptions; 3 repository Protocols.
- **Provider abstraction** (`src/application/market_data/provider.py`, `src/infrastructure/market_data/providers/`): `HistoricalDataProvider`/`RealtimeQuoteProvider`/`MarketDataProvider` Protocols; `YFinanceProvider` (dev, live-verified against real network calls) and `AlphaVantageProvider` (prod-ready interface, `GLOBAL_QUOTE` live-verified via the public demo key, `TIME_SERIES_DAILY` built from official docs but not live-verified — demo key rejects it); `ProviderRouter` with ordered failover.
- **Persistence**: Alembic migration `0003_market_data.py` (`ohlcv_bars`, `corporate_actions`, non-partitioned — disclosed below); `SqlAlchemyInstrumentRepository`/`SqlAlchemyOhlcvBarRepository`/`SqlAlchemyCorporateActionRepository` with bulk upsert; `MarketDataCache` (redis-cache instance, 30s TTL — disclosed below).
- **Application layer**: `MarketDataValidationService` (reject invalid prices/OHLC/volume); 6 use cases (`GetCurrentPrice`, `GetHistoricalPrices`, `GetOhlcvBars`, `GetCorporateActions`, `GetMarketStatus` [new], `SearchInstruments` [added mid-phase, see §3 item 1]).
- **Background sync**: Celery (`celery_app.py`, `tasks.py`) — `run_sync_pipeline()` (fetch → validate/dedupe → normalize → persist), live-verified end-to-end up to the expected Postgres-unavailable failure point.
- **Portfolio integration (key deliverable)**: `RealPriceProvider` implements Portfolio's existing `PriceProvider` Protocol exactly per `NullPriceProvider`'s documented upgrade path; DI wiring in `portfolio_use_cases.py` now constructs `RealPriceProvider` — Portfolio's Current Value/Unrealized Gain/Daily Gain/Allocation % now use real OHLCV data, with zero changes to `PortfolioCalculationService` or any Portfolio use case.
- **Presentation layer**: `market_data_router.py` — 6 REST endpoints (search, quote, prices, bars, corporate-actions, market/status), 11 Pydantic DTOs, centralized exception mapping, DI wiring. All endpoints unauthenticated by disclosed design (see §4).
- **ADR-0002 and ADR-0003**: both ratified to **Accepted** this phase (were Proposed at the end of Phase 3).

Frontend (`apps/web`):
- API client (`lib/market-data-api.ts`) — unauthenticated (`publicRequest`), covers all 6 endpoints.
- TanStack Query hooks (`features/market-data/hooks/useMarketData.ts`) — `useCurrentPrice` (30s refetch matching backend cache TTL), `useHistoricalPrices`, `useOhlcvBars`, `useCorporateActions`, `useMarketStatus` (60s refetch), `useInstrumentSearch`.
- 5 components (`features/market-data/components/`): `PriceChart` (line, adjusted-close), `OhlcvChart` (candlestick, lightweight-charts v5), `LiveQuote` (gain/loss colored), `StockSearch` (debounced), `InstrumentDetails` (composite: quote + chart-mode toggle + corporate actions).
- Pages: `/markets` (search landing), `/markets/[symbol]` (instrument detail) — deliberately placed outside `/dashboard` since market data is public (see §4).

## 2. Test Evidence

| Suite | Count | Result |
|---|---|---|
| Backend unit (domain: entities/value objects) | 28 | ✅ all passing |
| Backend unit (application: providers/router/validation/use cases/market status) | 40 | ✅ all passing |
| Backend unit (infrastructure: Alpha Vantage/RealPriceProvider/Celery tasks) | 18 | ✅ all passing |
| Backend unit (pre-existing, regression check) | 204 | ✅ all passing, zero regressions |
| Backend integration (Postgres via testcontainers) | 14 | ⚠️ written + statically verified, **not executed** (Docker unavailable) |
| Frontend unit (web, new market-data components) | 14 | ✅ all passing |
| Frontend unit (web, pre-existing, regression check) | 25 | ✅ all passing, zero regressions |
| Frontend E2E (Playwright, new `/markets` flows) | 5 | ✅ all passing |
| Frontend E2E (pre-existing, regression check) | 11 | ✅ all passing, zero regressions |

**Totals: 290 backend automated tests executed + 14 written-not-executed** (304 total backend); **39 frontend unit + 16 E2E** (55 total frontend). Zero regressions to Phase 1–3 (auth, portfolio) across both stacks at every incremental step (test counts grew monotonically: 204 → 232 → 249 → 280 → 285 → 290 on the backend; 25 → 39 on frontend unit; 11 → 16 on E2E).

## 3. Real Defects/Gaps Found and Fixed (via execution, not inspection)

| # | Defect/Gap | Category | Fix |
|---|---|---|---|
| 1 | `StockSearch` frontend component (explicit founder requirement) had no backend endpoint to call — the founder's original Phase 4 backend list named 5 APIs, but Document 4's frozen catalog independently specifies `GET /instruments/search?q=` and the frontend cannot function without it | A | Added `SearchInstrumentsUseCase` (thin wrapper over `InstrumentRepository.search()`, which already existed since task 5), DTOs, DI wiring, and the router endpoint; confirmed via live route inspection (31→ now 6 market-data paths incl. search) |
| 2 | `redis.asyncio`'s type stubs resolve `hgetall`/`hset`/`expire`'s return type ambiguously (a stub gap, not present for `get`/`incr`/`delete`/`ttl` used elsewhere) | B | Explicit `cast(Awaitable[...], ...)` documenting the true runtime type, scoped, commented |
| 3 | SQLAlchemy 2 async `Result[Any]` for UPDATE statements has no `.rowcount` attribute in the type stubs, despite the runtime `CursorResult` genuinely having one | B | Scoped `# type: ignore[attr-defined]` with an explanatory comment, not a blanket suppression |
| 4 | `yfinance`/`celery` have no `py.typed` markers (stub gap, same category as pre-existing `testcontainers`) | B | `[[tool.mypy.overrides]]` entries with `ignore_missing_imports = true` and an explanatory comment each |
| 5 | Test mocks for `LiveQuote`/`InstrumentDetails` used a fabricated response shape (extra `as_of` field on `CurrentPriceResponse`; missing `interval`/`data_completeness`/`adjusted_close`/`volume`/`is_closed`/`source`/`announced_at` fields elsewhere) | A (test code only) | Caught by `pnpm typecheck`; fixed by reading the real `lib/market-data-api.ts` interfaces and correcting every mock to match exactly |
| 6 | React `act()` warnings in `StockSearch.test.tsx` (unwrapped `vi.advanceTimersByTime`) and `InstrumentDetails.test.tsx` (raw `.click()` instead of `fireEvent.click()`) | A (test code only) | Wrapped timer advances in `act()`; switched to `fireEvent.click()` throughout |
| 7 | `pnpm build` fails at the Windows standalone-output symlink step (`EPERM`) | C (OS limitation) | Not fixable — identical to Phase 3's row 7 finding; compile/typecheck/static-generation (incl. the 2 new `/markets` pages) all succeed before the failing step |
| 8 | Backend integration tests, Celery-against-real-Postgres, Docker-dependent flows | D (environment) | Docker not installed — carried forward from Phase 1; written and statically verified but not executed |
| 9 | Alpha Vantage `TIME_SERIES_DAILY` cannot be live-verified | D (external tooling — no paid API key available) | Built from official docs' numbered-key convention; demo key genuinely rejects this endpoint (confirmed live) |

## 4. Disclosed Limitations (Carried Forward + New)

- **Docker unavailable** (Category D, Phase 1 origin): blocks all integration tests (14 new + 15 existing = 29 total written-not-executed) and Celery/Postgres end-to-end verification.
- **`ohlcv_bars` built as a single non-partitioned table**, not `PARTITION BY RANGE(bar_time)` from day one as the frozen DDL specifies — no partition-maintenance job exists yet; all access goes through `OhlcvBarRepository`, so partitioning is a migration-only upgrade with zero application-code change.
- **Mongo raw-snapshot persistence and Redis Pub/Sub event publishing** (ingestion pipeline stages 4b/5) not built — neither Mongo nor a Pub/Sub consumer exists anywhere in this codebase; both are additive when built (`run_sync_pipeline()`'s dependency-injection design was built specifically to accommodate this later).
- **Historical backfill is synchronous inline, not an enqueued Celery job** with a `backfill:inflight` dedupe flag — `GetOhlcvBarsUseCase` fetches/persists directly on a coverage gap rather than returning immediately with a background job in flight; no async job-status/polling contract exists on the frontend yet to support the originally-described progressive UX.
- **30-second quote cache TTL**, narrower than the frozen "no explicit invalidation, sub-second staleness via continuous overwrite" model — that model assumes a continuously-streaming WebSocket source this phase doesn't build; the TTL is the interim safety net between polls.
- **`PolygonProvider` (paid, real-time tier) not built** — no budget/API key; the `MarketDataProvider` Protocol is provider-count-agnostic, so this is additive when a paid provider is available.
- **`GetMarketStatusUseCase` has no holiday calendar** — correctly detects weekday market hours (9:30–16:00 ET, live-verified against real time) but does not know about market holidays.
- **Dividend corporate actions do not adjust historical prices** (`backward_adjustment_factor()` returns `1.0` for dividends) — genuine total-return adjustment requires reinvestment-assumption math beyond a simple ratio; only splits/reverse-splits currently adjust `adjusted_close`.
- **Frontend raw/adjusted price toggle not built** — charts always render adjusted values; the backend already returns both raw and adjusted fields where applicable, so this is a frontend-only addition later.
- **All 6 market-data endpoints are unauthenticated** (no bearer token) — a disclosed design decision (public reference data, matches the frozen catalog's lack of an auth annotation on `/instruments/*`/`/market/*`), confirmed in the actual generated OpenAPI spec (no `security` requirement present). Flagged as needing its own ADR if the founder wants these routes gated behind auth later.
- **`fundamentals`, `/market/heatmap`, `/market/indices` endpoints not built** — no schema or consumer exists for them yet; out of the founder's explicit Phase 4 list.
- **No shared dashboard navigation shell exists** to link to `/markets` — `dashboard/page.tsx` still just redirects to `/dashboard/portfolios`; inventing a nav shell was out of this phase's scope.

## 5. Architecture Fidelity

- No frozen table, column, or endpoint was removed or retyped. All changes are additive (new `market/status` and `instruments/search` endpoints; the `bars`/`prices` split is a deliberate two-endpoint refinement of one catalogued path, not a removal — both are documented in the Document 4 annotation).
- Clean Architecture dependency rule maintained across all 3 bounded contexts (`auth`, `portfolio`, `market_data`): domain has zero framework imports; `market_data_router.py` never talks to infrastructure directly; `RealPriceProvider` correctly sits in infrastructure implementing an application-layer Protocol.
- `InstrumentId` shared (not duplicated) between `portfolio` and `market_data` bounded contexts — this is why `RealPriceProvider` required zero ID-conversion glue code, a genuine benefit of the frozen schema's original design.
- Decimal discipline maintained end-to-end for all prices/quantities, including provider adapters (`float → str() → Decimal`, never `Decimal(float)` directly) and the frontend (decimal strings over the wire).
- Redis 3-way split honored (`redis-cache` for `MarketDataCache`, `redis-broker` for Celery), Alembic, FastAPI DI, Pydantic, TanStack Query, `lightweight-charts` (per Document 8's explicit roadmap naming) — all continued per the standing library-preference directives.
- Both ADR-0002 and ADR-0003 ratified to **Accepted** this phase — no outstanding architecture decisions awaiting founder response.

## 6. Recommendation

**Approve Phase 4.** No blocking follow-up conditions.

**Optional, non-blocking follow-ups** (install when feasible, not required to proceed):
1. Install Docker to execute the 29 written-but-unexecuted integration tests (15 from Phase 3 + 14 from Phase 4) and verify Celery-against-real-Postgres end-to-end.
2. Obtain a paid Alpha Vantage (or equivalent) API key to live-verify `TIME_SERIES_DAILY` and unlock the "Growth" real-time tier's `PolygonProvider`.
3. Consider whether the unauthenticated market-data design (§4) should be revisited via its own ADR before a public launch, if rate-limiting/abuse protection for anonymous traffic becomes a concern.

**Next phase options**, per Document 8's roadmap:
- **Watchlist** (remaining scope from the original "Phase 4 — Portfolio & Watchlist Core"): straightforward CRUD, same patterns as Portfolio, now able to show real prices/quotes via the `RealPriceProvider`/market-data endpoints just built.
- **AI/ML Pipeline features** (Document 4/8, e.g. forecasting, sentiment, recommendations): now unblocked by real historical OHLCV data existing in Postgres, which any prediction feature engineering would depend on.
- **Alerts** (price alert triggers, named in Document 8's roadmap): now unblocked by real-time quote polling existing.

**Watchlist is the stronger recommendation** — it is the most directly adjacent remaining scope, reuses the exact same patterns (repository/service/DTO/component conventions) already established twice (Portfolio, Market Data), and gives users a natural way to track instruments using the real search/quote/chart components just built.
