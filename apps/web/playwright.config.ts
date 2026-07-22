import { defineConfig, devices } from "@playwright/test";

// NOTE (Category D — external tooling limitation, see docs/phase-1/known-issues.md):
// `pnpm start` requires a production build, and `next build`'s standalone-output
// file-tracing step fails on this Windows development machine (EPERM on symlink
// creation — requires Developer Mode/admin, not present here). Locally, the E2E
// webServer runs `next dev` instead, which exercises the same rendered page and
// verifies the Playwright test logic itself is correct. The authoritative
// production-build E2E path is the Docker container (Linux, no symlink
// limitation) — see docker-compose verification in the Phase 1 report.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: {
    command: process.env.CI ? "pnpm start" : "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
