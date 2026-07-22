# Phase 1 — Environment

Records the actual verification environment, since several fixes and known issues in this phase are environment-specific (Windows, missing tools) rather than application defects.

## Operating System

Windows (PowerShell 5.1 default shell; `conda` auto-activation hook present and firing a harmless but noisy error on every shell invocation — pre-existing system configuration, unrelated to this project, not modified).

## Tooling Versions (as actually verified during this session)

| Tool | Version | Notes |
|---|---|---|
| Python (system default `python`) | 3.10.0 | Below the architecture's original `^3.12` target — see ADR-0001 |
| Python (via `py -3.11`) | 3.11.9 | Used for all Poetry environments this phase — see ADR-0001 |
| Python 3.12 | Not installed | Not present anywhere on this machine; Docker images still target `python:3.12-slim` per Document 7 §17.3, unaffected by ADR-0001 |
| Poetry | 2.4.1 (installed under Python 3.11 during this session) | 2.3.2 was already present under Python 3.10 but unusable for this project's `>=3.11` constraint until installed under 3.11 |
| Node.js | v22.21.0 | Pre-installed |
| npm | 11.8.0 | Pre-installed |
| pnpm | 11.15.1 | Installed during this session via `npm install -g pnpm` |
| Turbo | 2.1.3 | Installed via `pnpm install` (workspace devDependency) |
| Docker | **Not installed** | Confirmed via `docker --version` returning "not recognized" — see Known Issues |
| Docker Compose | **Not installed** | Same as above (ships with Docker Desktop) |

## Actions Taken to Prepare the Environment

1. `python -m pip install --user poetry` — found Poetry 2.3.2 already present under the Python 3.10 environment, but unusable directly (see below).
2. `py -3.11 -m pip install poetry` — installed Poetry 2.4.1 under Python 3.11, which is what all `poetry install`/`poetry run` commands in this phase actually used.
3. `npm install -g pnpm` — installed pnpm 11.15.1 globally.
4. `pnpm exec playwright install chromium --with-deps` — downloaded Chromium 130.0.6723.31 and FFMPEG build v1010 for Playwright E2E testing.

None of these are system-level installs requiring admin privileges or a restart; all are user-scoped and reversible (`pip uninstall`, `npm uninstall -g`, deleting the Playwright browser cache directory).

## Explicitly Not Done

- **Docker Desktop was not installed.** This is a substantial system-level install (typically requires enabling WSL2/Hyper-V and a restart on Windows) and was treated as a decision requiring the founder's explicit action, not something to install unilaterally mid-session, per the standing safety guardrails governing this implementation.
- **Windows Developer Mode was not enabled.** This would resolve the Next.js standalone-build symlink issue (see `known-issues.md`) but is a system security-posture setting change, likewise left to the founder rather than silently changed.
