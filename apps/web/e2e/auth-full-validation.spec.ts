import { expect, test } from "@playwright/test";

/**
 * Full authentication E2E validation, post-BFF-cookie-implementation.
 * Verifies the checklist: register, login, dashboard access, refresh
 * token (httpOnly cookie), logout, browser refresh (session persists),
 * protected routes, expired access token, refresh flow, middleware.
 */

const EMAIL = `auth-bff-${Date.now()}@investiq.local`;
const PASSWORD = "TestPass123!";
const FULL_NAME = "Auth BFF Test";

test.describe.serial("Full authentication E2E validation (BFF cookie architecture)", () => {
  test("register", async ({ page }) => {
    const responses: { status: number; body: string }[] = [];
    page.on("response", async (res) => {
      if (res.url().includes("/api/v1/auth/register")) {
        responses.push({ status: res.status(), body: await res.text().catch(() => "") });
      }
    });

    await page.goto("http://localhost:3000/register", { waitUntil: "networkidle" });
    await page.getByLabel("Full name").fill(FULL_NAME);
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Confirm password").fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await page.waitForTimeout(2000);

    console.log("RESULT_register:", JSON.stringify(responses[0]));
    expect(responses[0]?.status).toBe(201);
  });

  test("[setup] mark email verified via direct DB update (no email service in this dev environment)", async () => {
    const { execSync } = await import("node:child_process");
    execSync(
      `$env:PGPASSWORD='postgres'; & 'C:\\md_salman\\INVEST_IQ\\.localdev\\postgres\\pgsql\\bin\\psql.exe' -h localhost -U postgres -d investiq -c "UPDATE users SET email_verified_at = now() WHERE email = '${EMAIL}';"`,
      { shell: "powershell.exe" }
    );
  });

  test("login + JWT access token in response + refresh token as HttpOnly cookie (not in response body)", async ({
    page,
  }) => {
    const loginResponses: { status: number; body: string; headers: Record<string, string> }[] = [];
    page.on("response", async (res) => {
      if (res.url().includes("/api/bff/login")) {
        loginResponses.push({
          status: res.status(),
          body: await res.text().catch(() => ""),
          headers: res.headers(),
        });
      }
    });

    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    await page.waitForTimeout(2000);

    console.log("RESULT_login:", JSON.stringify(loginResponses[0]));
    expect(loginResponses[0]?.status).toBe(200);

    const bodyText = loginResponses[0]?.body ?? "{}";
    const parsedBody = JSON.parse(bodyText) as Record<string, unknown>;
    expect(parsedBody.access_token).toBeTruthy();
    // The refresh token must NEVER appear in the JSON response body —
    // it should only ever exist as the httpOnly cookie.
    expect(parsedBody.refresh_token).toBeUndefined();

    const cookies = await page.context().cookies();
    const refreshCookie = cookies.find((c) => c.name === "investiq_refresh_token");
    console.log("RESULT_refresh_cookie:", JSON.stringify(refreshCookie));
    expect(refreshCookie).toBeTruthy();
    expect(refreshCookie?.httpOnly).toBe(true);
    expect(refreshCookie?.sameSite).toBe("Strict");
  });

  test("dashboard access after login (client-side navigation, matching real user behavior)", async ({
    page,
  }) => {
    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    // LoginForm's onSuccess calls router.push (SPA navigation) —
    // wait for the resulting URL rather than forcing our own navigation.
    await page.waitForURL(/\/dashboard/, { timeout: 8000 });
    console.log("RESULT_dashboard_url:", page.url());
    expect(page.url()).toContain("/dashboard");
    expect(page.url()).not.toContain("/login");
  });

  test("browser refresh: session persists on a full page reload (the actual bug this BFF implementation fixes)", async ({
    page,
  }) => {
    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    await page.waitForURL(/\/dashboard/, { timeout: 8000 });

    // Full hard reload — this is exactly what previously logged the user
    // out (useAuthStore is in-memory-only) and is exactly what
    // useSilentSessionBootstrap + the BFF cookie now fix.
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    console.log("RESULT_url_after_reload:", page.url());
    expect(page.url()).not.toContain("/login");
    expect(page.url()).toContain("/dashboard");
  });

  test("protected routes: unauthenticated user is redirected by middleware (server-side, cookie-based)", async ({
    browser,
  }) => {
    // Fresh, cookie-less browser context — simulates a visitor who has
    // never logged in, hitting middleware.ts's server-side gate directly.
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("http://localhost:3000/dashboard/portfolios", { waitUntil: "networkidle" });
    console.log("RESULT_protected_route_url:", page.url());
    expect(page.url()).toContain("/login");
    expect(page.url()).toContain("redirectTo");
    await context.close();
  });

  test("logout clears the HttpOnly cookie and dashboard becomes unreachable again", async ({
    page,
  }) => {
    await page.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
    await page.getByLabel("Email").fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    await page.waitForURL(/\/dashboard/, { timeout: 8000 });

    const cookiesBeforeLogout = await page.context().cookies();
    expect(cookiesBeforeLogout.find((c) => c.name === "investiq_refresh_token")).toBeTruthy();

    const logoutButton = page.getByRole("button", { name: /log ?out|sign ?out/i }).first();
    await logoutButton.click();
    await page.waitForURL(/\/login/, { timeout: 8000 });

    const cookiesAfterLogout = await page.context().cookies();
    const refreshCookieAfterLogout = cookiesAfterLogout.find(
      (c) => c.name === "investiq_refresh_token"
    );
    console.log("RESULT_cookie_after_logout:", JSON.stringify(refreshCookieAfterLogout));
    expect(refreshCookieAfterLogout).toBeUndefined();

    // Middleware must now reject dashboard access again (server-side,
    // cookie-based — not just the client-side store having cleared).
    await page.goto("http://localhost:3000/dashboard/portfolios", { waitUntil: "networkidle" });
    console.log("RESULT_url_after_logout_dashboard_attempt:", page.url());
    expect(page.url()).toContain("/login");
  });

  test("refresh flow: rotation + old token rejected + expired/garbage access token rejected by core-api", async ({
    request,
  }) => {
    const loginResp = await request.post("http://127.0.0.1:8001/api/v1/auth/login", {
      data: { email: EMAIL, password: PASSWORD },
    });
    expect(loginResp.status()).toBe(200);
    const loginBody = (await loginResp.json()) as { refresh_token: string };
    const firstRefreshToken = loginBody.refresh_token;

    const refreshResp = await request.post("http://127.0.0.1:8001/api/v1/auth/refresh", {
      data: { refresh_token: firstRefreshToken },
    });
    expect(refreshResp.status()).toBe(200);
    const refreshBody = (await refreshResp.json()) as { refresh_token: string };
    console.log("RESULT_rotation_differs:", firstRefreshToken !== refreshBody.refresh_token);
    expect(refreshBody.refresh_token).not.toBe(firstRefreshToken);

    const reuseResp = await request.post("http://127.0.0.1:8001/api/v1/auth/refresh", {
      data: { refresh_token: firstRefreshToken },
    });
    console.log("RESULT_old_token_reuse_status:", reuseResp.status());
    expect(reuseResp.status()).toBe(401);

    const expiredLikeToken =
      "eyJhbGciOiJIUzI1NiIsImtpZCI6ImRlZmF1bHQiLCJ0eXAiOiJKV1QifQ." +
      Buffer.from(
        JSON.stringify({
          sub: "00000000-0000-0000-0000-000000000000",
          role: "user",
          token_version: 0,
          iat: 1000000000,
          exp: 1000000001,
          jti: "00000000-0000-0000-0000-000000000000",
        })
      ).toString("base64url") +
      ".invalidsignature";
    const expiredResp = await request.get("http://127.0.0.1:8001/api/v1/portfolios", {
      headers: { Authorization: `Bearer ${expiredLikeToken}` },
    });
    console.log("RESULT_expired_token_status:", expiredResp.status());
    expect(expiredResp.status()).toBe(401);
  });
});
