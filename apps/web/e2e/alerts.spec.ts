import { expect, test } from "@playwright/test";

/**
 * Phase 6 E2E: alerts dashboard route protection. Same honest-scope
 * rationale as e2e/watchlist.spec.ts — core-api/Postgres are not running
 * here (Docker unavailable, Category D carried forward), so this test
 * verifies the CLIENT-SIDE routing behavior genuinely works, not a full
 * authenticated round-trip against a live backend. Alerts are auth-gated
 * (private per-user resources), matching watchlist.spec.ts's exact
 * pattern.
 */

test.describe("Alerts dashboard routes", () => {
  test("protected /dashboard/alerts redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard/alerts");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard%2Falerts/);
  });
});
