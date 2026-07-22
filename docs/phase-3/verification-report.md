# Phase 3 Verification Report — Portfolio Management

**Status:** Complete and verified. **Recommendation: approve Phase 3 with 3 explicit follow-up conditions** (see §6).

## 1. Scope Delivered

Backend (`apps/core-api`, Clean Architecture — domain/application/infrastructure/presentation):
- **Domain layer**: `Portfolio` aggregate root, `Holding`, `Transaction` (8 types), `Money`/`Quantity` Decimal-backed value objects, 9 domain exceptions, repository Protocols with pagination/filter support.
- **Persistence**: Alembic migration `0002_portfolio_context.py` (instruments/portfolios/holdings/transactions), SQLAlchemy models, `SqlAlchemyPortfolioRepository`/`SqlAlchemyTransactionRepository`.
- **Application layer**: 9 use cases (Create/Get/List/Update/Delete Portfolio, AddTransaction, ListTransactions, GetHoldings, GetPortfolioSummary), `PortfolioCalculationService` (all 10 requested calculations).
- **Presentation layer**: 9 REST endpoints (full CRUD + transactions + holdings + summary), 11 Pydantic DTOs, centralized exception mapping, DI wiring.
- **ADR-0003**: extends `transactions.type` with `split`/`transfer_in`/`transfer_out` — additive only, drafted and **Proposed**, awaiting founder ratification (same status as ADR-0002).

Frontend (`apps/web`, `packages/validation`):
- Zod schemas (`createPortfolioSchema`, `updatePortfolioSchema`, `addTransactionSchema` — single discriminated schema for all 8 transaction types).
- 4 components: `PortfolioSummaryCards`, `HoldingsTable`, `TransactionHistory`, `AddTransactionDialog` — TanStack Query, RHF+Zod, `motion`, explicit loading/error/empty states.
- Dashboard pages: `/dashboard/portfolios` (list+create), `/dashboard/portfolios/[id]` (detail, wiring all 4 components); `/dashboard` now forwards into the real dashboard.

## 2. Test Evidence

| Suite | Count | Result |
|---|---|---|
| Backend unit (domain) | 55 | ✅ all passing |
| Backend unit (application: calculations + use cases) | 44 | ✅ all passing |
| Backend unit (pre-existing auth, regression check) | 105 | ✅ all passing, zero regressions |
| Backend integration (Postgres via testcontainers) | 7 | ⚠️ written + statically verified, **not executed** (Docker unavailable) |
| Frontend unit (validation package) | 35 (22 new) | ✅ all passing |
| Frontend unit (web components, new) | 11 | ✅ all passing |
| Frontend unit (web, pre-existing, regression check) | 14 | ✅ all passing, zero regressions |
| Frontend E2E (Playwright) | 11 (3 new) | ✅ 11/11 at reduced parallelism |

**Totals: 264 automated tests passing** (backend 204 executed + 7 written-not-executed; frontend 60 unit + 11 E2E), zero regressions to the frozen auth module across both stacks.

## 3. Real Defects Found and Fixed (via execution, not inspection)

| # | Defect | Category | Fix |
|---|---|---|---|
| 1 | `Transaction.price` for `DIVIDEND` was ambiguous (per-share vs. lump sum); dividend income was computed as `price` alone, ignoring `quantity` | A | Added explicit validation requiring both fields; dividend income = `price × quantity` |
| 2 | Split-adjusted `total_cost_basis` drifts by up to 1e-8/share for non-exact ratios (e.g. 1:3) | A (inherent, not fixable) | Test bounds the drift to the smallest representable unit; a separate exact-ratio test proves zero drift when the ratio divides evenly |
| 3 | `renderWithQueryClient` test helper: TS2742 inferred-type-not-portable error | A | Added explicit `RenderResult` return type |
| 4 | `packages/ui` design tokens missing `success`/`text-secondary` — first surfaced by Phase 3's need for gain/loss coloring | A | Added tokens to `colors.ts`, `tailwind.preset.js`, `globals.css`; verified no regression to existing Button tests |
| 5 | 18 pre-existing mypy `--strict` errors in frozen auth test files (`FakeVerificationTokenStore` Protocol variance) | B (pre-existing, unrelated) | **Not fixed** — auth is frozen; confirmed reproducible in isolation with zero Phase 3 files in scope, masked in Phase 2 because `mypy --strict tests/` was never run as a single whole-tree sweep |
| 6 | `ruff format --check` flags 10 pre-existing frozen-auth files (cosmetic line-wrap drift) | B (pre-existing, unrelated) | **Not fixed** — confirmed via diff it's purely cosmetic (ruff formatter version drift since Phase 2), zero functional impact |
| 7 | `pnpm build` fails at the Windows standalone-output symlink step (`EPERM`) | C (OS limitation) | Not fixable — confirmed compile/typecheck/static-generation all succeed before the failing step; `output: "standalone"` is a frozen Document 7 §17.3 decision correct for the target Linux container |
| 8 | 2 pre-existing auth E2E tests flake under 8-worker Playwright parallelism | D (tooling/resource contention) | Not fixable — both pass in isolation and the full suite passes 11/11 at reduced parallelism |
| 9 | Backend integration tests, frontend Docker-dependent flows | D (environment) | Docker not installed — carried forward from Phase 1/2, written and statically verified but not executed |

## 4. Disclosed Limitations (Carried Forward + New)

- **Docker unavailable** (Category D, Phase 1 origin): blocks all `docker build`/`compose`, and the 7 new + 8 existing integration tests.
- **BFF httpOnly-cookie layer not built** (Phase 2 origin): `middleware.ts`'s server-side redirect check still doesn't have a real cookie to check; dashboard route protection is currently client-side-guard only, same disclosed gap as Phase 2.
- **ADR-0002 and ADR-0003 both awaiting founder ratification** — neither formally Accepted yet.
- **Roadmap resequencing**: Document 8 labels "Phase 3" as Market Data Foundation; Portfolio Management was built as Phase 3 per explicit founder direction. Documented in `08-coding-standards-git-roadmap.md` as a sequencing change, not an architecture change.
- **`/performance?range=1y` endpoint not implemented** — depends on `ohlcv_bars`, not yet built (Market Data Foundation). The new `/summary` endpoint serves current-moment calculations only, not historical time-series.
- **`PriceProvider` is a null stub** (`NullPriceProvider`) — Current Value/Unrealized Gain/Allocation %/Daily Gain gracefully degrade (reported via `holdings_missing_price`) rather than crash or silently show zero, pending the real Market Data Foundation implementation. No changes needed to the calculation service or any use case when that lands.
- **Pre-existing mypy/format drift in frozen auth files** (items 5–6 above) — disclosed, not fixed, per the explicit auth-freeze instruction.

## 5. Architecture Fidelity

- No frozen table, column, or endpoint was removed or retyped. All changes are additive (ADR-0002, ADR-0003).
- Clean Architecture dependency rule maintained: domain has zero framework imports; portfolio_router.py never talks to infrastructure directly.
- Money/Quantity Decimal discipline maintained end-to-end, including the frontend (decimal strings, never floats, over the wire).
- Redis 3-way split, structlog, SQLAlchemy 2 async, Alembic, FastAPI DI, Pydantic, React Query, Zod, `motion` — all continued per the standing library-preference directives.

## 6. Recommendation

**Approve Phase 3**, conditioned on:
1. Founder ratifies or rejects ADR-0002 (`login_history`) and ADR-0003 (split/transfer transaction types) — both currently Proposed.
2. Acknowledge the roadmap resequencing note in Document 8, or direct a correction if the sequencing was not intended to be permanent.
3. Install Docker when feasible, to execute the 15 written-but-unexecuted integration tests and finally verify graceful shutdown (Category C item, carried from Phase 1).

**Next phase options**, per the resequencing now in place:
- **Market Data Foundation** (Document 8's original Phase 3 scope): `instruments` population, `ohlcv_bars`, `corporate_actions`, provider integration, real `PriceProvider` — this unblocks Current Value/Unrealized Gain/Allocation %/Daily Gain for Portfolio Management, which currently degrade gracefully but produce no real numbers.
- **Watchlist** (remaining Phase 4 scope): straightforward CRUD, same patterns as Portfolio.

Market Data Foundation is the stronger recommendation — it directly completes what Portfolio Management already depends on and unblocks the dashboard's most visible currently-degraded numbers.
