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

  it("calls the BFF logout route (same-origin, credentials included) with the given access token as a Bearer header", async () => {
    // logoutCurrentSession now always calls the BFF's /api/bff/logout
    // route handler — it holds no refresh-token state of its own
    // (the refresh token lives exclusively server-side, in the httpOnly
    // cookie app/api/bff/logout/route.ts reads directly). The BFF route
    // itself decides whether there's anything to revoke server-side;
    // this client-side call is unconditional.
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 204,
      json: async () => undefined,
    } as Response);

    await authApi.logoutCurrentSession("current-access-token");

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const call = vi.mocked(global.fetch).mock.calls[0];
    const [url, options] = call ?? [];
    expect(String(url)).toBe("/api/bff/logout");
    expect(options?.credentials).toBe("include");
    expect((options?.headers as Record<string, string>).Authorization).toBe(
      "Bearer current-access-token"
    );
  });
});
