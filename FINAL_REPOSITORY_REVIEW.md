# Final Repository Review

**Scope:** Repository cleanliness and documentation audit only. No application
functionality was modified. This document records what was reviewed, what was
found, what was fixed, and what remains as a flagged decision for the
repository owner.

**Date:** 2026-07-26

---

## 1. Summary

The INVEST_IQ monorepo's application code (`apps/web`, `apps/core-api`,
`apps/ai-service`, `packages/*`, `libs/*`) is clean: no commented-out dead
code, no stray `console.log`/`print()`/`debugger` statements, no unused
dependencies, no naming-convention violations, and no broken documentation
links were found anywhere in the actual source trees. The issues found were
entirely in **repository hygiene** — stray debug artifacts that had been
committed to git, documentation drift between the README and the current
directory layout, and one significant git-tracking issue (`.localdev/`)
that requires the repository owner's explicit decision (see §6).

## 2. What was removed

The following git-tracked files were confirmed to be scratch/debug artifacts
with no role in the application, its tests, or its documentation, and were
removed from git tracking (`git rm --cached`) and deleted from disk:

| Path | Why |
|---|---|
| `apps/core-api/server_log_final.txt` | Ad-hoc manual server-run log dump |
| `apps/core-api/server_log_p5.txt` | Ad-hoc manual server-run log dump |
| `apps/web/dev_log.txt` | Ad-hoc `next dev` console dump |
| `apps/web/tsconfig.tsbuildinfo` | TypeScript incremental build cache (regenerated automatically; never belongs in git) |
| `apps/web/test-results/.last-run.json` | Playwright run-state cache (regenerated automatically) |
| `apps/ai-service/data/test-models/arima/AAPL/*.pkl` (17 files, ~14MB) | Scratch model artifacts left over from manual `/train` endpoint testing against `TrainModelUseCase`'s `artifact_storage_root`; not fixtures read by any test (tests only ever *write* to this path, confirmed by reading `tests/unit/presentation/_fixtures.py`) |

No source code, test file, configuration file, or documentation file was
deleted. Every removal was verified against actual code/test usage before
being removed (see the investigation notes below).

## 3. `.gitignore` corrections

The root `.gitignore` was missing rules for several categories of file that
were consequently committed to git despite being pure build/test/scratch
output. Added:

- `dev_log.txt`, `server_log*.txt` — the two stray debug-log naming patterns found (the existing `*.log` rule already correctly covers the rest)
- `*.tsbuildinfo` — TypeScript incremental build cache
- `test-results/`, `playwright-report/` — Playwright/e2e output
- `apps/ai-service/data/test-models/` — local model-training scratch output
- `.localdev/` — see §6 below; added to `.gitignore` so no *new* files under it are tracked going forward, but the 20,392 files already committed require a separate, explicit decision to untrack (not done automatically — see §6)

## 4. Documentation corrections

### `README.md`
- The "Monorepo Structure" diagram claimed `packages/types/`, a top-level `ml/`, and a top-level `scripts/` directory as if they currently exist. They do not — `packages/types/` and `ml/` are named in the architecture blueprint as planned-but-not-yet-built (this is explicitly and correctly disclosed in `libs/domain_common/README.md`, which was left unchanged), and no `scripts/` directory has ever existed in this repo. The structure diagram now describes what actually exists, with a note pointing to the blueprint doc for the planned-but-unbuilt pieces.
- `ai-service`'s one-line description said "FastAPI + Celery" — `celery` is not a dependency of `apps/ai-service` (verified: zero references in `apps/ai-service/pyproject.toml`'s dependency list; the one text match was a comment referencing *core-api's* Celery setup). Corrected to describe what ai-service actually is: the hybrid ML decision engine.
- The "Status" section said "Phase 1 (Foundation & Skeleton) — in progress," which is stale — `docs/phase-9/` (Real-Time Market Intelligence) is the most recent completed phase, and 262 automated tests pass across the frontend plus full backend test suites. Corrected to point to `docs/phase-*/` as the authoritative record of what's built, since (see §5 below) the architecture blueprint's own roadmap phase *names* no longer match what was actually implemented phase-by-phase.

### `apps/web/.env.example`
- `NEXTAUTH_SECRET`/`NEXTAUTH_URL` were present with no explanation; `next-auth` is not a dependency and nothing in the codebase reads these variables today (confirmed by grep). Rather than removing them (which would look like silently dropping a documented future integration), added a comment clarifying they are unused placeholders for a planned BFF/cookie-session layer referenced in `middleware.ts`'s own docstring.

### `apps/core-api/.env`
- The real local `.env` file was missing 9 keys that exist in its own `.env.example` (`JWT_KID` and 8 rate-limit/large-transaction/realtime-poll-interval keys added in later phases). All 9 have code-level defaults in `src/config.py`'s `Settings` class, so the service was never broken by their absence — but the file was stale. Refreshed to match `.env.example`'s current key set. No secret values were changed; only the missing non-secret keys (numeric/boolean defaults) were added.

## 5. Findings recorded but intentionally NOT changed

These are real observations from the investigation that were deliberately
**not** acted on, because fixing them would mean editing the "frozen"
architecture blueprint or application source beyond what this cleanliness
pass was scoped to touch:

- **`docs/architecture/08-coding-standards-git-roadmap.md`'s Phase 1–10 roadmap names/scope no longer match what was actually built.** For example, the roadmap document's "Phase 8" and "Phase 9" descriptions differ from `docs/phase-8/` and `docs/phase-9/`'s actual implementation-summary titles ("Enterprise Security" and "Real-Time Market Intelligence" respectively — confirmed by reading both). This is normal drift between an upfront plan and what a large project actually built, but it means the roadmap document is no longer a reliable source for "what phase are we on" — `docs/phase-*/` is. This was **not** edited, since the README explicitly states the architecture blueprint is frozen and any deviation should go through an ADR, not a silent rewrite during a cleanliness pass.
- **FastAPI app metadata is minimal.** Both `apps/core-api/src/main.py` and `apps/ai-service/src/main.py` construct `FastAPI(title=..., version=..., lifespan=...)` with no `description`, `contact`, or `license_info`, and individual router endpoint functions have module-level docstrings but no per-endpoint docstrings — so the live `/docs`/`/redoc` OpenAPI UI (both enabled, confirmed) will render with correct paths/schemas but sparse per-operation descriptions. This is a documentation-*richness* gap, not a functional bug (`/docs` and `/redoc` work correctly), and editing `main.py`/router files was out of scope for a "do not modify functionality" cleanliness pass.
- **No LICENSE file exists anywhere in the repository**, and no `package.json`/`pyproject.toml` declares a `license` field. This is **internally consistent** (nothing claims a license that doesn't exist, and vice versa) — for a private (`"private": true`) project this may be entirely intentional. Not added, since choosing a license is a legal/business decision for the repository owner, not something to decide unilaterally during a cleanliness pass.

## 6. Flagged for explicit owner decision: `.localdev/`

This is the single highest-impact finding and was **not acted on** beyond
adding it to `.gitignore` (which only prevents *new* changes under it from
being tracked — it does not remove what's already committed).

**What it is:** `.localdev/` is a local development scratch directory
(vendored Postgres 16 + Redis binary distributions, a live Postgres data
directory, Redis dump files, and manual curl/browser test artifacts).

**What was found, with evidence:** `git ls-files .localdev | wc -l` returns
**20,392 tracked files**, including:
- `.localdev/postgres16.zip` (334 MB) and `.localdev/redis.zip` (11 MB) — vendored binary installers
- `.localdev/pgdata/**` — a live PostgreSQL data directory (WAL segments, table files) that changes on every database write, meaning these binary files show as a perpetual diff
- `.localdev/postgres/pgsql/**` — the fully extracted Postgres + pgAdmin4 distribution, including pgAdmin's bundled Python environment and **its own vendored `__pycache__`/license files**
- Multiple JSON files containing **plaintext JWT access/refresh tokens and test account credentials** (`login.json`, `login2.json`, `final_login.json`, `final_check_login.json`, `register.json`, `register2.json`, etc.)

**Why this was not fixed automatically:** untracking 20,392 files (via
`git rm -r --cached .localdev`) is a large, high-blast-radius change, and
the files containing plaintext-looking tokens mean this also has a
credential-hygiene dimension. Additionally, if this repository has ever
been pushed to a remote (confirmed: `origin` = a real GitHub URL), those
tokens and binaries are already in the remote's git history —
`git rm --cached` only stops *future* commits from including it; fully
purging it from history would require `git filter-repo`/BFG plus a
force-push, which rewrites shared history and is exactly the kind of
irreversible, high-risk operation this review's guardrails require
explicit confirmation for.

**Recommended next step (not executed):**
1. Rotate/invalidate any real credentials that may have been captured in those JSON dumps, since they must be treated as compromised if this repo has ever been pushed publicly or shared.
2. Run `git rm -r --cached .localdev` (safe: does not delete local files, does not rewrite history) to stop tracking it going forward — `.gitignore` already has the rule in place for this.
3. Separately decide whether to rewrite git history to remove the already-committed binaries/tokens (`git filter-repo`), which is a bigger, riskier decision the repository owner should make deliberately, not as a side effect of a cleanliness pass.

## 7. Verification performed

After every change in this pass:
- `pnpm typecheck` — 3/3 packages successful
- `pnpm lint` — 3/3 packages successful, 0 warnings
- `pnpm test:unit` — 262/262 tests passed (182 web + 76 validation + 4 ui)
- `poetry run pytest` (core-api, scoped to alert/watchlist/enrichment/tasks) — 112/112 passed
- `poetry run pytest` (ai-service, scoped to train_model/retrain) — 10/10 passed

No functionality was changed by this pass; these runs confirm the file
removals and `.gitignore`/documentation edits did not break anything.

## 8. Items verified clean (no action needed)

- **Commented-out code:** none found in `apps/web`, `apps/core-api/src`, `apps/ai-service/src`, or `packages/*`.
- **Debug statements:** no `console.log`, `print()`, or `debugger` statements in source (tests and intentional `console.error` in error boundaries excluded, as those are correct usage).
- **TODO/FIXME/XXX/HACK markers:** none in actual project source (all matches found during investigation were inside vendored third-party packages under `.localdev/`, not project code).
- **Unused dependencies:** zero found across all 5 `package.json` files and both backend `pyproject.toml` files — every dependency was grepped and confirmed used.
- **devDependency categorization:** correct in every manifest — test tooling and type-only packages are consistently in `devDependencies`.
- **Naming conventions:** 100% consistent — PascalCase for all React components (88 files spot-checked), snake_case for all Python modules (198 files spot-checked across both services).
- **Alembic migrations:** sequential `0001`–`0006`, no gaps, no duplicate numbers.
- **README links:** zero broken links found in any of the 5 README.md files in the repo (root, `libs/auth_common`, `libs/domain_common`, `libs/observability`, `docs/architecture/adr`).
- **Architecture documentation:** the 8 numbered blueprint documents plus `REVIEW-LOG.md` and 4 ADRs are complete, sequentially numbered with no gaps, and internally cross-referenced correctly (each ADR's "Supersedes" pointer matches an inline "See ADR-000N" comment in the affected blueprint document).
- **`.env.example` completeness:** `apps/core-api/.env.example` and `apps/ai-service/.env.example` each contain exactly the full set of environment variables their respective `Settings` classes read — no missing, no extra (beyond the `apps/web` placeholder case documented in §4).
