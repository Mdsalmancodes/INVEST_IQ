import { expect, test } from "@playwright/test";

/**
 * Phase 8 E2E: role-gated admin panel visibility on the AI Insights
 * dashboard. Same honest-scope rationale as e2e/ai.spec.ts and every
 * other spec in this directory — core-api is not running here (Docker
 * unavailable, Category D carried forward), so a real login (which
 * requires a live core-api to issue a JWT) cannot be exercised at the
 * browser level. This spec therefore verifies what IS testable without
 * a backend: an unauthenticated visitor is redirected before ever
 * reaching the page, so the admin panel (features/ai/components/
 * ModelStatus.tsx's ModelAdminPanel, gated by RequireRole) is
 * necessarily never rendered for them. The authenticated/role-gated
 * rendering paths themselves are covered by real component-level unit
 * tests instead (ModelStatus.test.tsx's "admin panel" describe block),
 * which can construct a real signed-looking JWT and populate
 * useAuthStore directly without needing a live backend.
 */

test.describe("AI dashboard admin panel — role gating", () => {
  test("an unauthenticated visitor is redirected before the admin panel could ever render", async ({
    page,
  }) => {
    await page.goto("/dashboard/ai");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard%2Fai/);
    await expect(page.getByText("Model Administration")).not.toBeVisible();
  });
});
