import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { aiApi } from "./ai-api";
import type { ApiError } from "./auth-api";
import { useAuthStore } from "../store/auth-store";

const originalFetch = global.fetch;

describe("aiApi", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("throws NOT_AUTHENTICATED without ever calling fetch when there is no access token", async () => {
    await expect(aiApi.getModelStatus()).rejects.toMatchObject({
      code: "NOT_AUTHENTICATED",
    } satisfies Partial<ApiError>);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("calls core-api's /api/v1/ai/* proxy (not ai-service's /api/v1/ml/*) with the Authorization header", async () => {
    useAuthStore.getState().setAccessToken("fake-access-token-for-header-check");
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ families: [] }),
    } as Response);

    await aiApi.getModelStatus();

    const [url, options] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    expect(String(url)).toContain("/api/v1/ai/models/status");
    expect(String(url)).not.toContain("/api/v1/ml/");
    expect((options?.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-access-token-for-header-check"
    );
  });

  it("sends DELETE /api/v1/ai/models/{id} for deleteModel", async () => {
    useAuthStore.getState().setAccessToken("token");
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => undefined,
    } as Response);

    await aiApi.deleteModel("11111111-1111-1111-1111-111111111111");

    const [url, options] = vi.mocked(global.fetch).mock.calls[0] ?? [];
    expect(String(url)).toContain("/api/v1/ai/models/11111111-1111-1111-1111-111111111111");
    expect(options?.method).toBe("DELETE");
  });

  it("surfaces a non-ok response (e.g. 403 for a non-admin calling an admin endpoint) as an ApiError", async () => {
    useAuthStore.getState().setAccessToken("token");
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        success: false,
        error: { code: "FORBIDDEN", message: "Insufficient role" },
      }),
    } as Response);

    await expect(aiApi.getModelStatus()).rejects.toMatchObject({
      code: "FORBIDDEN",
      status: 403,
    });
  });
});
