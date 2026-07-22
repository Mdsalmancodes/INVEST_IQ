# Phase 1 — Fixes Applied

Every code/config change made in response to a real verification failure, grouped by root cause. Cross-reference `verification-log.md` for the exact command sequence and `known-issues.md` for anything left unresolved.

## Category A — Application Defects

### A1. Deprecated `typing.AsyncIterator` import (Ruff `UP035`)
**Where:** `apps/core-api/src/main.py`, `apps/ai-service/src/main.py`
**Fix:** `ruff check --fix` replaced with `collections.abc.AsyncIterator`.

### A2. Import sorting / line length (Ruff `I001`, `E501`)
**Where:** `apps/core-api/alembic/env.py`, `apps/core-api/src/infrastructure/persistence/postgres/session.py`
**Fix:** `ruff check --fix` + `ruff format`.

### A3. `require()` in a TypeScript file (ESLint `@typescript-eslint/no-require-imports`)
**Where:** `apps/web/tailwind.config.ts`
**Root cause:** `packages/config/tailwind.preset.js` was CommonJS (`module.exports`), imported via `require()`.
**Fix:** Converted `tailwind.preset.js` to ESM (`export default`), converted the consuming file to a proper `import`.

### A4. Missing jest-dom type augmentation (`tsc` `TS2339`)
**Where:** `apps/web/tsconfig.json`
**Root cause:** `@testing-library/jest-dom`'s global `expect` matcher augmentation (`toBeInTheDocument`, etc.) requires explicit inclusion in `compilerOptions.types` — it worked in `packages/ui` incidentally but not in `apps/web`, which extends a different base config chain.
**Fix:** Added `"types": ["@testing-library/jest-dom"]` to `apps/web/tsconfig.json`.

### A5. Vitest JSX transform mismatch (`ReferenceError: React is not defined`)
**Where:** `apps/web/vitest.config.ts`
**Root cause:** Next.js's `tsconfig.json` sets `jsx: "preserve"` (required — Next's own compiler handles JSX transformation). Vitest doesn't go through Next's compiler; it needs its own esbuild JSX setting, which wasn't configured, so JSX was left untransformed at runtime.
**Fix:** Added `esbuild: { jsx: "automatic" }` to Vitest's config, independent of the Next tsconfig setting (which was correctly left unchanged).

### A6. Vitest picking up Playwright spec files
**Where:** `apps/web/vitest.config.ts`
**Root cause:** Vitest's default test-file glob matched `e2e/home.spec.ts`, which imports Playwright's `test`/`expect` — calling Playwright's `test()` outside its own runner throws.
**Fix:** Added `exclude: ["**/node_modules/**", "**/e2e/**"]` to Vitest config.

### A7. Missing `py.typed` marker causing `mypy --strict` `import-untyped`
**Where:** `libs/observability`
**Root cause:** A package with type hints but no `py.typed` marker file is treated by mypy as untyped by default (PEP 561) — this silently degraded type-checking for every consumer (`core-api`, `ai-service`) of this shared library, not just a cosmetic warning.
**Fix:** Added `observability/py.typed` (empty marker file) and `include = ["observability/py.typed"]` to `pyproject.toml` so it ships with the package.

### A8. structlog `Processor` type signature mismatches (`mypy --strict`)
**Where:** `libs/observability/observability/redaction.py`, `logger.py`
**Root cause:** Our custom structlog processors (`redaction_processor`, `_add_service_name`'s inner `processor`) were typed with a narrower/inconsistent signature (`dict[str, Any]` return, `object`/`Any` for the logger param) than structlog's actual `Processor` type alias (`(WrappedLogger, str, MutableMapping[str, Any]) -> Mapping[str, Any] | str | bytes | ...`), causing "list item has incompatible type" errors when placed in `structlog.configure(processors=[...])`.
**Fix:** Rewrote both processors' signatures to match structlog's `Processor` type exactly (`MutableMapping[str, Any]` param and return type), added an `assert isinstance(result, dict)` after calling `redact()` (which returns `Any` since it's recursive over heterogeneous data) to satisfy `no-any-return` without a blanket suppression.

## Category B — Dependency/Version Issues

### B1. `python = "^3.12"` unsatisfiable on this machine
**Where:** `apps/core-api/pyproject.toml`, `apps/ai-service/pyproject.toml`, `libs/observability/pyproject.toml`
**Fix:** Relaxed to `>=3.11,<3.13`; formally recorded as **ADR-0001** (`docs/architecture/adr/0001-python-3.11-local-dev-compatibility.md`) since this touches the frozen architecture's implied tooling target. Docker images remain pinned to `python:3.12-slim`, unaffected.

### B2. `@testing-library/react@16.0.1` unmet peer dependency on React 19
**Where:** `apps/web/package.json`, `packages/ui/package.json`
**Fix:** Bumped to `16.1.0`, the first version with React 19 RC peer-range support (confirmed via web search before applying, not guessed).

### B3. `packages/config` missing its own runtime dependencies
**Where:** `packages/config/package.json`
**Root cause:** `eslint-base.js` imports `@eslint/js`, `typescript-eslint`, `eslint-plugin-jsx-a11y` directly, but the package never declared them — worked accidentally nowhere, failed everywhere it was actually consumed.
**Fix:** Added all three as `dependencies`; also added `"type": "module"` since the file uses ESM `import`/`export` syntax.

### B4. Missing `tailwindcss`/`@types/react`/`@types/react-dom`/`@next/eslint-plugin-next` as explicit dependencies
**Where:** `apps/web/package.json`, `packages/ui/package.json`
**Root cause:** Several packages were used directly (imported, or referenced via config) without being declared — either assumed-transitive (risky) or simply forgotten during initial scaffolding.
**Fix:** Added each as an explicit dependency at the correct level (dependency vs. devDependency, matching how it's actually used).

## Fixes Considered and Rejected

### `.npmrc` `symlink=false` (attempted fix for the Next.js standalone-build issue, Category D)
**Why rejected:** caused unrelated `postinstall` script failures (`unrs-resolver`, `esbuild` platform-binary resolution) because those scripts expect pnpm's normal symlinked `node_modules` layout. The workaround traded one documented, understood, non-blocking issue for multiple new ones. Reverted; the underlying issue is documented in `known-issues.md` as Category D instead.
