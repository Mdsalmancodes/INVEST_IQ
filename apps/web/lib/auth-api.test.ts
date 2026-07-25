import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "./auth-api";

const originalFetch = global.fetch;

describe("authApi.logoutCurrentSession", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("does nothing if there is no refresh token in memory (never logged in this session)", async () => {
    await authApi.logoutCurrentSession("some-access-token");
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("sends the Authorization header with the given access token when a refresh token is held", async () => {
    // Populate the module-level refresh token via a real login call first.
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "initial-access-token",
        refresh_token: "held-refresh-token",
        token_type: "bearer",
      }),
    } as Response);
    await authApi.login({ email: "user@example.com", password: "correct-horse-battery-staple" });

    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => undefined,
    } as Response);

    await authApi.logoutCurrentSession("current-access-token");

    const logoutCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes("/api/v1/auth/logout")
    );
    expect(logoutCall).toBeDefined();
    const [, options] = logoutCall ?? [];
    expect((options?.headers as Record<string, string>).Authorization).toBe(
      "Bearer current-access-token"
    );
  });
});
