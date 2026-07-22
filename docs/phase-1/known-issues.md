# Phase 1 — Known Issues

Issues identified during Phase 1 verification that remain unresolved, classified per the failure-category scheme (A/B fixed already — see `fixes-applied.md`; this document covers C and D only, plus any accepted technical debt).

## Category C — Operating System Limitations

### C1. Graceful shutdown not verifiable via Windows background-process termination
**What:** Stopping a `uvicorn`-served FastAPI process on Windows via `Stop-Process` (with or without `-Force`) or `CloseMainWindow()` does not reliably trigger the same signal Python's asyncio/uvicorn graceful-shutdown handling expects on Linux (`SIGTERM`/`SIGINT` to a foreground process group). No `service.shutdown` structured log line was observed following termination attempts.
**Why this is not an application defect:** The `lifespan` shutdown handler (`apps/core-api/src/main.py`, `apps/ai-service/src/main.py`) is implemented correctly per Document 2 §5.3's app-factory pattern — the code path is simple and correct (`logger.info("service.shutdown")` after `yield`). The issue is entirely in how Windows delivers (or fails to deliver) termination signals to a background process started via `Start-Process -RedirectStandardOutput`, which is not equivalent to a Linux process receiving `SIGTERM` in its own process group.
**Resolution path:** The Docker container (Linux) is the authoritative environment for this verification, per explicit instruction — `docker stop` sends a real `SIGTERM` to PID 1 inside the container, which uvicorn handles correctly. **This has not yet been verified because Docker is unavailable in this environment (see D2 below).** Tracked as outstanding until Docker becomes available.
**Architecture impact:** None. No change to the frozen architecture is implied or needed.

### C2. Anaconda/conda shell hook noise on every command
**What:** Every shell command in this environment prefixes its output with a harmless `EnvironmentNameNotFound: Could not find conda environment: proctifyAI` error and a PowerShell `Invoke-Expression` binding error, originating from a pre-existing Anaconda PowerShell profile hook unrelated to this project.
**Impact:** Cosmetic only — does not affect any command's actual exit code or stdout content (verified throughout this session: real exit codes and real stdout were used for every pass/fail determination, never inferred from the presence/absence of this noise).
**Resolution path:** Out of scope for this project — would require modifying the user's global PowerShell profile / Anaconda configuration, not something this implementation should touch.

## Category D — External Tooling Limitations

### D1. Next.js `output: "standalone"` build fails on this Windows machine (EPERM on symlink creation)
**What:** `next build` compiles successfully and generates all static pages (confirmed via real build output: "✓ Compiled successfully", "✓ Generating static pages (4/4)"), but fails during the standalone-output file-tracing step, which attempts to create filesystem symlinks to deduplicate `node_modules` into the standalone bundle. Windows requires Developer Mode or administrator privileges to create symlinks; neither is available in this environment.
**Why this is not an application defect:** Confirmed via web research as a well-documented, widely-reported interaction between Next.js's standalone output tracer, pnpm's symlink-heavy `node_modules` structure, and Windows's symlink permission model (see e.g. `vercel/next.js` discussion #52244). Multiple independent sources confirm the same root cause and the same two real fixes (Developer Mode, or `pnpm config set symlink=false`).
**Workaround attempted and rejected:** `symlink=false` in `.npmrc` was tried and found to break unrelated `postinstall` scripts (`unrs-resolver`, `esbuild`'s platform-binary resolution) that depend on pnpm's normal symlinked layout — a worse tradeoff than leaving the original issue documented. Reverted.
**Impact on Phase 1 verification:**
  - `pnpm build` (workspace-wide, via Turbo): **fails at the `apps/web` standalone-trace step specifically.** `packages/ui` and `packages/config` are unaffected (no such build step). The underlying Next.js application code is confirmed correct up through page generation.
  - Playwright E2E: worked around locally by running against `next dev` instead of `next start` (which requires the failed build) — this verifies the E2E test logic and the rendered page are correct, but is **not** the production-build code path.
  - Docker: **unaffected** — the `apps/web/Dockerfile`'s builder stage runs on Linux (`node:20-alpine`), which has no symlink permission restriction. This is the authoritative build-verification path once Docker is available (see D2).
**Architecture impact:** None. `output: "standalone"` remains correct per Document 7 §17.3 and is not being reconsidered — this is a local Windows dev-environment limitation, not a reason to change the containerization strategy.
**Resolution path:** Either (a) founder enables Windows Developer Mode, or (b) rely exclusively on the Docker build path for standalone-output verification (recommended — matches how this actually ships in every real environment: CI and production are Linux).

### D2. Docker / Docker Compose not installed
**What:** `docker --version` and `docker compose version` both return "not recognized" — Docker Desktop is not installed on this machine.
**Impact:** `docker build`, `docker compose config`, and `docker compose up` could not be executed. This blocks:
  - Direct confirmation that `apps/core-api/Dockerfile`, `apps/ai-service/Dockerfile`, `apps/web/Dockerfile` actually build successfully.
  - `docker compose config`'s full schema validation of `infra/docker-compose.yml` (only a generic YAML-syntax check was possible instead — see below).
  - End-to-end container boot + `/health`/`/ready` verification against the real containerized services.
  - Resolution of C1 (graceful shutdown) via the authoritative Linux-container path.
**Partial substitute validation performed:** `infra/docker-compose.yml` was parsed with Python's `pyyaml` library and confirmed to be syntactically valid YAML, containing all 8 expected services (`postgres`, `redis-cache`, `redis-broker`, `redis-session`, `mongo`, `core-api`, `ai-service`, `web`) and 4 named volumes. **This does not validate Compose-schema-specific semantics** (e.g., whether `depends_on.condition: service_healthy` or the `profiles` list syntax is well-formed per Compose's actual spec) — only `docker compose config` can do that.
**Manual review performed:** Both Dockerfiles were re-read against Document 7 §17.3's requirements (multi-stage, non-root `USER`, `HEALTHCHECK`, pinned base image versions) — structurally compliant on inspection, but **inspection is not execution**, and this is explicitly flagged as such rather than presented as equivalent to a real `docker build`.
**Architecture impact:** None. No architecture change proposed or needed.
**Resolution path:** Founder installs Docker Desktop (a substantial system-level install, typically requiring WSL2/Hyper-V enablement and a restart on Windows) — left as an explicit decision for the founder rather than performed unilaterally, per the standing safety guardrails.

### D3. `react-remove-scroll` (transitive dependency of `@radix-ui/react-dialog`) unmet peer dependency on React 19
**What:** `pnpm install` reports an unmet peer dependency warning: `react-remove-scroll@2.6.0` expects `react@"^16.8.0 || ^17.0.0 || ^18.0.0"`, but React 19 (RC) is installed.
**Why this is not fixable by us:** This is a transitive dependency pulled in by Radix UI's `Dialog` primitive, not a direct dependency we control the version of. As of this session, no released version of `react-remove-scroll` declares React 19 support.
**Impact:** Warning only — `pnpm install` succeeds, and no functional breakage has been observed (the `Dialog` primitive is not yet implemented/used in any Phase 1 code, so this has not been exercised at runtime). Flagged for re-verification once `Dialog` is actually built out (Document 8 roadmap, later phase) and once the Radix/React 19 ecosystem catches up (React 19 was in RC status at the time of this session).
**Architecture impact:** None.

## Accepted Technical Debt (not blockers, tracked for future phases)

- **Lighthouse CI, contract-testing CI job, resilience/chaos test suite** (all specified in the architecture review, Documents 6-7) are not yet implemented — correctly deferred, per the roadmap (Document 8 §24), to Phase 5/6/10 respectively, not Phase 1.
- **`packages/types` and `packages/validation`** exist only as directory placeholders in the folder structure — no shared Zod schemas or generated OpenAPI types exist yet, correctly deferred to Phase 2 (Identity & Access) when the first real API contract exists to generate types from.
