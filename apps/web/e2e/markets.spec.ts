import { expect, test } from "@playwright/test";

/**
 * Phase 4 E2E: public /markets routes. Unlike portfolio.spec.ts, these
 * routes are NOT behind middleware.ts's auth gate (matcher only covers
 * /dashboard/:path*) — market data is intentionally public per
 * market_data_router.py's disclosed unauthenticated design. Same honest-
 * scope rationale as the other e2e specs: core-api/Postgres are not
 * running here (Docker unavailable, Category D), so these tests verify
 * client-side rendering/navigation genuinely works, not a full live data
 * round-trip. Error states are asserted where a live backend would be
 * required (search results, quote data) since those genuinely cannot
 * succeed without the backend running.
 */

test.describe("Markets routes", () => {
  test("/markets is reachable without authentication (no redirect to login)", async ({
    page,
  }) => {
    await page.goto("/markets");
    await expect(page).toHaveURL(/\/markets$/);
    await expect(page.getByRole("heading", { name: "Markets" })).toBeVisible();
  });

  test("/markets renders the stock search input", async ({ page }) => {
    await page.goto("/markets");
    await expect(page.getByLabel(/search for a stock/i)).toBeVisible();
  });

  test("typing in the search box shows a result state (error, since no backend is running)", async ({
    page,
  }) => {
    await page.goto("/markets");
    await page.getByLabel(/search for a stock/i).fill("AAPL");
    // No live core-api in this E2E environment (Category D) - the search
    // request itself will fail, which is a genuinely testable client-side
    // behavior: the error state must render, not crash the page.
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 5_000 });
  });

  test("/markets/[symbol] is reachable without authentication and shows the symbol heading", async ({
    page,
  }) => {
    await page.goto("/markets/AAPL");
    await expect(page).toHaveURL(/\/markets\/AAPL$/);
    await expect(page.getByRole("heading", { name: "AAPL" })).toBeVisible();
  });

  test("/markets/[symbol] shows a back-to-search link", async ({ page }) => {
    await page.goto("/markets/AAPL");
    const backLink = page.getByRole("link", { name: /back to search/i });
    await expect(backLink).toBeVisible();
    await backLink.click();
    await expect(page).toHaveURL(/\/markets$/);
  });
});
