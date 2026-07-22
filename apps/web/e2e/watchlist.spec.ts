import { expect, test } from "@playwright/test";

/**
 * Phase 5 E2E: watchlist dashboard route protection. Same honest-scope
 * rationale as e2e/portfolio.spec.ts — core-api/Postgres are not running
 * here (Docker unavailable, Category D carried forward), so these tests
 * verify the CLIENT-SIDE/middleware routing behavior genuinely works, not
 * a full authenticated round-trip against a live backend. Watchlists are
 * auth-gated (unlike Phase 4's public /markets pages), matching
 * portfolio.spec.ts's exact pattern.
 */

test.describe("Watchlist dashboard routes", () => {
  test("protected /dashboard/watchlists redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard/watchlists");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard%2Fwatchlists/);
  });

  test("protected watchlist detail route redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard/watchlists/11111111-1111-1111-1111-111111111111");
    await expect(page).toHaveURL(
      /\/login\?redirectTo=%2Fdashboard%2Fwatchlists%2F11111111-1111-1111-1111-111111111111/
    );
  });
});
