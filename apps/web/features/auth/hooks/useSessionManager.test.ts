import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "../../../lib/auth-api";
import { useAuthStore } from "../../../store/auth-store";
import { useSessionManager } from "./useSessionManager";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("../../../lib/auth-api", () => ({
  authApi: {
    refreshAccessToken: vi.fn(),
    logoutCurrentSession: vi.fn().mockResolvedValue(undefined),
  },
}));

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(role: string, exp: number): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64UrlEncode(JSON.stringify({ sub: "u", role, exp }));
  return `${header}.${body}.fake-signature`;
}

describe("useSessionManager", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does nothing while logged out", () => {
    renderHook(() => useSessionManager());
    vi.advanceTimersByTime(60 * 60 * 1000);
    expect(authApi.refreshAccessToken).not.toHaveBeenCalled();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("proactively refreshes the access token before it expires and updates the store", async () => {
    const exp = Math.floor(Date.now() / 1000) + 15 * 60; // 15 minutes from now
    useAuthStore.getState().setAccessToken(makeToken("user", exp));

    const newExp = Math.floor(Date.now() / 1000) + 30 * 60;
    const newToken = makeToken("user", newExp);
    vi.mocked(authApi.refreshAccessToken).mockResolvedValue({
      access_token: newToken,
      refresh_token: "rotated-refresh",
      token_type: "bearer",
    });

    renderHook(() => useSessionManager());

    // Refresh is scheduled for (expiresAt - 2min); advance just past that.
    await vi.advanceTimersByTimeAsync(13 * 60 * 1000 + 1000);

    expect(authApi.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBe(newToken);
  });

  it("logs out and redirects to /login if the proactive refresh call fails", async () => {
    const exp = Math.floor(Date.now() / 1000) + 15 * 60;
    useAuthStore.getState().setAccessToken(makeToken("user", exp));
    vi.mocked(authApi.refreshAccessToken).mockRejectedValue(new Error("refresh token revoked"));

    renderHook(() => useSessionManager());

    await vi.advanceTimersByTimeAsync(13 * 60 * 1000 + 1000);

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("logs out and redirects to /login after the idle timeout with no activity", async () => {
    const exp = Math.floor(Date.now() / 1000) + 60 * 60; // far in the future, refresh not the trigger here
    useAuthStore.getState().setAccessToken(makeToken("user", exp));

    renderHook(() => useSessionManager());

    await vi.advanceTimersByTimeAsync(30 * 60 * 1000 + 1000);

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("resets the idle timer on activity, avoiding logout", async () => {
    const exp = Math.floor(Date.now() / 1000) + 24 * 60 * 60; // far enough out that proactive refresh never triggers in this test
    useAuthStore.getState().setAccessToken(makeToken("user", exp));

    renderHook(() => useSessionManager());

    // Just before the idle timeout, simulate activity.
    await vi.advanceTimersByTimeAsync(29 * 60 * 1000);
    act(() => {
      window.dispatchEvent(new Event("keydown"));
    });

    // Advance by another 29 minutes (would have exceeded the original
    // 30-minute deadline if the timer hadn't been reset).
    await vi.advanceTimersByTimeAsync(29 * 60 * 1000);

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
