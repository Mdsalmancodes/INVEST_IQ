import { expect, test } from "@playwright/test";

/**
 * Phase 3 E2E: portfolio dashboard route protection. Same honest-scope
 * rationale as e2e/auth.spec.ts — core-api/Postgres are not running here
 * (Docker unavailable, Category D carried forward), so these tests verify
 * the CLIENT-SIDE/middleware routing behavior genuinely works, not a full
 * authenticated round-trip against a live backend.
 */

test.describe("Portfolio dashboard routes", () => {
  test("protected /dashboard/portfolios redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard/portfolios");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard%2Fportfolios/);
  });

  test("protected portfolio detail route redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard/portfolios/11111111-1111-1111-1111-111111111111");
    await expect(page).toHaveURL(
      /\/login\?redirectTo=%2Fdashboard%2Fportfolios%2F11111111-1111-1111-1111-111111111111/
    );
  });

  test("/dashboard forwards to the portfolios dashboard (still gated by middleware)", async ({
    page,
  }) => {
    // /dashboard itself now redirect()s to /dashboard/portfolios (Phase 3),
    // but middleware.ts's matcher covers /dashboard/:path* so the
    // unauthenticated redirect to /login still fires correctly end-to-end.
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard/);
  });
});
