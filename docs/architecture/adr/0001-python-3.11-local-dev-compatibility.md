# ADR-0001: Python 3.11 for Local Development, Python 3.12 Preserved as Production/Docker Target

**Status:** Accepted
**Date:** 2026-07-21
**Supersedes/amends:** Document 7 (`07-devops-cicd-deployment-scalability.md`) §17.3 Dockerfile examples (`FROM python:3.12-slim`), and the `pyproject.toml` files in `apps/core-api`, `apps/ai-service`, `libs/observability` as originally scaffolded with `python = "^3.12"`.

## Context

During Phase 1 infrastructure verification, the actual development machine was found to have Python 3.10.0 as the default interpreter and Python 3.11.9 available via the Windows `py` launcher — Python 3.12 is not installed anywhere on this machine. The original `pyproject.toml` files (written directly from the architecture blueprint's Docker examples, which specify `python:3.12-slim` base images) pinned `python = "^3.12"`, which made `poetry install` fail to resolve on this machine without a Python 3.12 installation.

This is a genuine environment/tooling blocker, not a design preference — the frozen architecture (Document 7 §17.3) does not mandate a specific Python minor version for local development, only that Docker images use pinned, specific base image versions for reproducibility. Local development interpreter version and containerized runtime version are already logically separate concerns in the blueprint; this ADR makes that separation explicit rather than papering over a version mismatch.

## Decision

- **Local development and CI test execution** use Python **3.11** (specifically 3.11.9, via `py -3.11` on Windows). All `pyproject.toml` files' `[tool.poetry.dependencies] python` constraint is relaxed to `">=3.11,<3.13"` (previously `"^3.12"`), and each `[tool.mypy] python_version` is set to `"3.11"` to match the interpreter actually running type-checking locally.
- **Docker images remain pinned to `python:3.12-slim`** exactly as specified in Document 7 §17.3 — this ADR does not change the production/container runtime target. The `>=3.11,<3.13` constraint is intentionally a *range*, not a pin, so the same lock-file-resolved dependency set installs correctly under either 3.11 (local) or 3.12 (Docker) without maintaining two separate dependency manifests.
- This is recorded as a **temporary** accommodation: if/when Python 3.12 is installed on development machines (or CI runners, which can trivially use `actions/setup-python` with `3.12` regardless of this ADR), the constraint can be tightened back to `^3.12` with no code changes required, since nothing in the Phase 1 codebase uses a Python 3.12-only language feature.

## Consequences

- **Easier:** `poetry install` succeeds on the actual development machine without requiring a new Python installation as a blocking prerequisite to any implementation work.
- **Harder / given up:** a genuine (small) risk that a 3.12-only stdlib feature or dependency version could be used by accident in future phases without a local 3.11 interpreter catching a real 3.12-vs-3.11 incompatibility — mitigated by CI running against the Docker image's actual Python 3.12 environment (via `docker build`, Document 7 §18.2) before merge, which is the authoritative compatibility check regardless of what version any individual developer runs locally.
- **Affected sections:** `apps/core-api/pyproject.toml`, `apps/ai-service/pyproject.toml`, `libs/observability/pyproject.toml` (all three `python` constraints and `mypy.python_version` settings) — each file carries no special comment marker beyond this ADR being the record of why the constraint is a range instead of a pin; Document 7 §17.3's Dockerfile examples are unaffected and remain the production source of truth.
- **Reversible:** yes — tightening back to `^3.12` once 3.12 is available locally is a one-line change per file, with no application code changes anticipated.

## Alternatives Considered

- **Install Python 3.12 on the development machine before continuing.** Rejected for now: installing a new Python version system-wide is a more invasive, less reversible action than relaxing a version constraint, and per the safety guardrails governing this implementation, installing new system-level software should be a deliberate, explicit choice by the founder rather than something done silently mid-implementation. The founder can choose to install 3.12 at any time, at which point this ADR's "temporary" framing resolves itself without further action.
- **Pin everything to 3.10 (the true system default) instead of 3.11.** Rejected: 3.11 is closer to the frozen architecture's 3.12 target (fewer version-gap risks), is available via the `py` launcher without any new installation, and is a currently-supported, non-EOL Python version, unlike stretching further back would risk.
- **Maintain two separate lock files/dependency manifests for local vs. Docker.** Rejected as unnecessary complexity — a single `>=3.11,<3.13` range resolves correctly for both environments with one lock file, per Poetry's own dependency resolution.
