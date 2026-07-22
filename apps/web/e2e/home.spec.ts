import { expect, test } from "@playwright/test";

/**
 * Phase 1 smoke test — verifies the Next.js app actually boots and renders
 * the packages/ui-consuming placeholder page end-to-end (real browser, real
 * server), per Document 6 §16.3's E2E tier. Full critical-journey E2E tests
 * (signup→dashboard, etc.) arrive as those features are built per the
 * roadmap (Document 8 §24) — this is intentionally minimal for Phase 1.
 */
test("home page renders and is interactive", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "INVEST IQ" })).toBeVisible();
  const button = page.getByRole("button", { name: "Get Started" });
  await expect(button).toBeVisible();
});
