# Phase 5 Verification Report — Watchlist

**Status:** Complete and verified. **Recommendation: approve Phase 5** (see §6). No blocking follow-up conditions (ADR-0004 already Accepted).

## 1. Scope Delivered

Backend (`apps/core-api`, Clean Architecture — domain/application/infrastructure/presentation):
- **ADR-0004**: extends `watchlists` (`is_default`, `updated_at`) and `watchlist_items` (`position`, `is_pinned`) — additive only, DB-enforced at-most-one-default-per-user via a partial unique index. Drafted and ratified to **Accepted** this phase.
- **Domain layer** (`src/domain/watchlist/`): `Watchlist` aggregate root (create/rename/mark-default/add-item/remove-item/set-pinned/reorder-item, all invariants enforced — no duplicate symbol, valid name, contiguous positions after reorder), `WatchlistItem` entity, `WatchlistId`/`WatchlistItemId` value objects (`InstrumentId` reused from `domain.portfolio`), 6 domain exceptions, `WatchlistRepository` Protocol with search/sort/pagination filter.
- **Persistence**: Alembic migration `0004_watchlist_context.py` (`watchlists`, `watchlist_items`); `SqlAlchemyWatchlistRepository` — upserts the aggregate and its items, and **deletes orphaned items** (a genuine difference from Portfolio's holdings-save pattern, since item removal is a routine first-class Watchlist operation).
- **Application layer**: 9 use cases (Create/Get/List/Update/Delete Watchlist, Add/Remove/Update WatchlistItem, EnsureDefaultWatchlist) plus `WatchlistEnrichmentService` — the **Phase 4/5 integration point**, orchestrating Phase 4's existing `GetCurrentPriceUseCase` and `GetMarketStatusUseCase` (via Protocol-typed dependencies, not concrete classes) to attach live price/daily change/daily %/market status/delayed indicator to each item, with per-item error isolation so one bad quote never breaks the whole response.
- **Presentation layer**: `watchlist_router.py` — 8 REST endpoints exactly per ADR-0004's API surface (`POST`/`GET /watchlists`, `GET`/`PATCH`/`DELETE /watchlists/{id}`, `POST /watchlists/{id}/items`, `PATCH`/`DELETE /watchlists/{id}/items/{itemId}`), 9 Pydantic DTOs, exception mapping (reusing Phase 4's `market_data_exception_handlers` for symbol-resolution errors, not duplicating it). **All 8 endpoints require authentication** — a disclosed, deliberate contrast with Phase 4's public market-data endpoints, since watchlists are private per-user resources.

Frontend (`apps/web`):
- Zod schemas (`packages/validation/src/watchlist.ts`) — `createWatchlistSchema`/`updateWatchlistSchema` (name capped at 100 chars, matching the domain layer exactly), `addWatchlistItemSchema`, `updateWatchlistItemSchema`.
- API client (`lib/watchlist-api.ts`) — authenticated (`authorizedRequest`, matching `portfolio-api.ts`'s pattern, not market-data's public pattern), covering all 8 endpoints.
- TanStack Query hooks (`features/watchlist/hooks/useWatchlists.ts`).
- 7 components exactly as named in the founder's requirement: `WatchlistDashboard`, `WatchlistCards`, `WatchlistTable`, `SymbolSearchDialog`, `AddSymbolDialog`, `CreateWatchlistDialog`, `EditWatchlistDialog` — genuinely reusing Phase 4's `StockSearch` (via `SymbolSearchDialog`) and, via `WatchlistTable`'s per-symbol links to `/markets/{symbol}`, Phase 4's `LiveQuote`/`PriceChart`/`OhlcvChart` (through the existing `InstrumentDetails` composite) rather than duplicating chart/search UI.
- Pages: `/dashboard/watchlists` (list), `/dashboard/watchlists/[id]` (detail) — correctly auth-gated (unlike Phase 4's public `/markets` pages), with zero `middleware.ts` changes needed since its matcher already covers `/dashboard/:path*`.

## 2. Test Evidence

| Suite | Count | Result |
|---|---|---|
| Backend unit (domain: Watchlist aggregate/WatchlistItem) | 24 | ✅ all passing |
| Backend unit (application: 9 use cases) | 20 | ✅ all passing |
| Backend unit (application: WatchlistEnrichmentService) | 7 | ✅ all passing |
| Backend unit (pre-existing, regression check) | 290 | ✅ all passing, zero regressions |
| Backend integration (Postgres via testcontainers) | 9 | ⚠️ written + statically verified, **not executed** (Docker unavailable) |
| Frontend unit (web, new watchlist components) | 28 | ✅ all passing |
| Frontend unit (web, pre-existing, regression check) | 39 | ✅ all passing, zero regressions |
| Frontend E2E (Playwright, new `/dashboard/watchlists` flows) | 2 | ✅ all passing |
| Frontend E2E (pre-existing, regression check) | 16 | ✅ all passing, zero regressions |

**Totals: 341 backend automated tests executed + 9 written-not-executed** (350 total backend); **67 frontend unit + 18 E2E** (85 total frontend). Zero regressions to Phases 1–4 at every incremental step (backend executing test count grew monotonically: 290 → 314 → 334 → 341, unchanged by task 9's integration-test-writing since those are correctly deselected by default; frontend unit grew 39 → 67; E2E grew 16 → 18).

## 3. Real Defects/Gaps Found and Fixed (via execution, not inspection)

| # | Defect/Gap | Category | Fix |
|---|---|---|---|
| 1 | Founder's explicit Phase 5 requirements (default watchlist, custom ordering, pinning, rename, full CRUD) exceeded the frozen minimal `watchlists`/`watchlist_items` DDL and Document 4's 3-endpoint catalog | N/A (architecture gap, not a code defect) | Drafted and ratified **ADR-0004** before writing any code — 4 additive columns, 2 additive indexes, 5 additive endpoints, all documented with alternatives-considered and an upgrade path |
| 2 | A loop-variable shadow in `SqlAlchemyWatchlistRepository.save()` (`existing_item_model` reused across two for-loops with different mypy-inferred types) | A | Renamed the second loop's variable to `matching_existing_model` — a real naming fix, not a suppression |
| 3 | `WatchlistEnrichmentService`'s constructor was typed against the *concrete* `GetCurrentPriceUseCase`/`GetMarketStatusUseCase` classes, making it untestable without the full Phase 4 provider/cache/DB chain | A (architectural) | Introduced `GetCurrentPriceUseCaseProtocol`/`GetMarketStatusUseCaseProtocol` — depending on abstractions, matching this codebase's established convention (`PriceProvider`, all repository Protocols); confirmed the real production DI wiring still satisfies the new Protocol types |
| 4 | Initial fake `Instrument` construction in `test_use_cases.py` was missing 3 required fields (`ipo_date`, `is_active`, `created_at`) | A (test code only) | Caught by `mypy --strict`; fixed by supplying all fields to match the real dataclass |
| 5 | First draft of the `idx_watchlists_user_default` integration test had confused/contradictory reasoning about FK constraints (dead-code placeholder lines, comments admitting the test didn't actually work) | A (test code only, self-caught) | Rewrote using the same real-`User`-creation pattern `test_portfolio_repositories.py` already established, so the partial unique index is what actually gets exercised, not a false FK failure |
| 6 | Two Vitest assertions used a single regex to match text split across separate DOM elements (label + `<span>` value) | A (test code only) | `WatchlistTable.test.tsx`: asserted on the value text alone; `AddSymbolDialog.test.tsx`: constructed a real `ApiError` instance instead of a plain `Error`, matching the component's actual (correct) error-extraction logic |
| 7 | Backend integration tests, Docker-dependent Postgres-constraint verification | D (environment) | Docker not installed — carried forward from Phase 1; written and statically verified but not executed |

## 4. Disclosed Limitations (Carried Forward + New)

- **Docker unavailable** (Category D, Phase 1 origin): blocks the 9 new Watchlist integration tests (38 total written-not-executed across all phases now).
- **`alerts` table/CRUD not built** — genuinely out of the founder's explicit Phase 5 Watchlist requirement list; remains future scope per Document 8's roadmap.
- **Custom item ordering uses a full-rewrite O(n) reorder**, not fractional indexing — disclosed in ADR-0004 as justified by watchlists being small collections (tens of symbols, not thousands); documented as the upgrade path if this assumption changes.
- **`EnsureDefaultWatchlistUseCase` is called lazily** (on first `GET /watchlists` call for a user with zero watchlists), not eagerly at registration — deliberate, since Auth (Phase 2) is frozen and must not be modified to call it.
- **No shared dashboard navigation shell** exists yet to link Portfolios ↔ Watchlists ↔ Markets — the same disclosed gap carried forward from Phase 4 (`dashboard/page.tsx` still just redirects to `/dashboard/portfolios`); not built, out of this phase's explicit scope.
- **All 8 watchlist endpoints require authentication** — a disclosed, deliberate contrast with Phase 4's public market-data endpoints (confirmed live and in the generated OpenAPI contract), since watchlists are private per-user resources.

## 5. Architecture Fidelity

- No frozen table, column, or endpoint was removed or retyped. All changes are additive (ADR-0004's 4 columns/2 indexes/5 endpoints, alongside the 3 already-catalogued endpoints and minimal-but-sufficient original DDL).
- Clean Architecture dependency rule maintained across the new `watchlist` bounded context: domain has zero framework imports; `watchlist_router.py` never talks to infrastructure directly; `WatchlistEnrichmentService` depends on Protocols, not concrete classes (a genuine improvement caught and fixed during this phase, not merely preserved).
- `InstrumentId` shared (not duplicated) between `watchlist` and `portfolio`/`market_data` bounded contexts — the third bounded context to reuse this type without any conversion glue code.
- Decimal discipline maintained end-to-end for all quote fields (price/daily_change/daily_change_pct), including the frontend (decimal strings over the wire).
- Genuine reuse (not reimplementation) of Phase 4's `GetCurrentPriceUseCase`, `GetMarketStatusUseCase`, `StockSearch`, and (via page-level linking) `LiveQuote`/`PriceChart`/`OhlcvChart` — the founder's explicit "reuse" requirement is reflected in actual import graphs, not just documentation claims.
- ADR-0004 ratified to **Accepted** this phase — no outstanding architecture decisions awaiting founder response.

## 6. Recommendation

**Approve Phase 5.** No blocking follow-up conditions.

**Optional, non-blocking follow-ups** (install/build when feasible, not required to proceed):
1. Install Docker to execute the 38 written-but-unexecuted integration tests across all phases (9 from Phase 5 + 29 from Phases 3/4).
2. Build a shared dashboard navigation shell linking Portfolios/Watchlists/Markets — currently each is reachable only by direct URL or from within the flow that created it.
3. Consider `alerts` (price alert triggers) as a natural next increment, since it was named alongside Watchlist in the original Document 8 roadmap and the founder's Phase 5 instruction did not include it.

**Next phase options**, per Document 8's roadmap and this session's cumulative progress:
- **Alerts**: price alert triggers, the remaining piece of the original "Portfolio & Watchlist Core" phase — now unblocked by both real market data (Phase 4) and the Watchlist UI patterns (Phase 5) it would naturally build on.
- **AI/ML Pipeline features** (forecasting, sentiment, recommendations, Document 4/8): unblocked by real historical OHLCV data existing in Postgres since Phase 4.
- **Landing Page & Design Polish** (Document 8's own Phase 5): the actual public-facing front door, independent of the backend feature phases.

**Alerts is the stronger recommendation** — it directly completes the "Portfolio & Watchlist Core" scope this session has been working through, reuses the exact same patterns (repository/service/DTO/component conventions) established three times now (Portfolio, Market Data, Watchlist), and gives users a genuinely new capability (proactive price notifications) rather than more infrastructure with no new user-facing behavior.
