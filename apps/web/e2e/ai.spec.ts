import { expect, test } from "@playwright/test";

/**
 * Phase 7 E2E: AI Insights dashboard route protection. Same honest-scope
 * rationale as e2e/watchlist.spec.ts and e2e/portfolio.spec.ts —
 * ai-service/core-api are not running here (Docker unavailable, Category
 * D carried forward), so this test verifies the CLIENT-SIDE routing
 * guard genuinely works, not a full round-trip against a live ai-service
 * backend. /dashboard/ai is guarded consistently with the rest of
 * /dashboard/* (see app/dashboard/ai/page.tsx's module docstring for the
 * disclosed distinction: this guard protects the page *route*, it does
 * not and cannot add authorization to ai-service's own unauthenticated
 * REST API — see docs/phase-7/known-issues.md).
 */

test.describe("AI Insights dashboard route", () => {
  test("protected /dashboard/ai redirects to login with redirectTo param", async ({ page }) => {
    await page.goto("/dashboard/ai");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard%2Fai/);
  });
});
