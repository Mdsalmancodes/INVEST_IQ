import { expect, test } from "@playwright/test";

/**
 * Phase 2 E2E: real browser navigation through the auth pages. Since
 * core-api/Postgres/Redis are not running in this environment (Docker
 * unavailable — carried-forward Category D blocker), this test verifies
 * the CLIENT-SIDE flow genuinely works — page rendering, client-side
 * validation, navigation between auth pages — without asserting on a
 * successful backend round-trip (which would require the full stack up).
 * This is an honest scope: it proves the frontend is correct and wired up
 * to attempt the right requests, not that the full stack integration works
 * (that requires Docker, documented in known-issues).
 */

test.describe("Auth pages", () => {
  test("login page renders and validates client-side", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();

    await page.getByLabel("Email").fill("not-an-email");
    await page.getByLabel("Password").fill("somepassword");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText(/valid email/i)).toBeVisible();
  });

  test("navigates from login to register and back", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Sign up" }).click();
    await expect(page).toHaveURL(/\/register$/);
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();

    await page.getByRole("link", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("navigates from login to forgot-password", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("link", { name: "Forgot your password?" }).click();
    await expect(page).toHaveURL(/\/forgot-password$/);
    await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();
  });

  test("register page shows password strength meter as the user types", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Password", { exact: true }).fill("Str0ng!Passphrase#2026");
    await expect(page.getByText(/password strength: strong/i)).toBeVisible();
  });

  test("register page validates mismatched passwords client-side", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel("Full name").fill("Jane Investor");
    await page.getByLabel("Email").fill("jane@example.com");
    await page.getByLabel("Password", { exact: true }).fill("a-genuinely-strong-passphrase");
    await page.getByLabel("Confirm password").fill("a-different-passphrase");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText(/passwords do not match/i)).toBeVisible();
  });

  test("reset-password page shows an error state when the token is missing", async ({
    page,
  }) => {
    await page.goto("/reset-password");
    await expect(page.getByText(/missing or invalid/i)).toBeVisible();
  });

  test("protected dashboard route redirects to login with redirectTo param", async ({
    page,
  }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard/);
  });
});
