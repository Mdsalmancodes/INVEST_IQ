import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "./auth-store";

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(payload: Record<string, unknown>): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64UrlEncode(JSON.stringify(payload));
  return `${header}.${body}.fake-signature`;
}

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
  });

  it("starts with no user, no token, unauthenticated", () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.expiresAt).toBeNull();
  });

  it("setAccessToken decodes and stores the user's id/role and the token's expiry", () => {
    const exp = Math.floor(Date.now() / 1000) + 900;
    const token = makeToken({ sub: "user-abc", role: "pro_user", exp });

    useAuthStore.getState().setAccessToken(token);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe(token);
    expect(state.user).toEqual({ userId: "user-abc", role: "pro_user" });
    expect(state.expiresAt).toBe(exp * 1000);
  });

  it("setAccessToken still marks the session authenticated even if the token fails to decode", () => {
    useAuthStore.getState().setAccessToken("not-a-real-jwt");

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user).toBeNull();
  });

  it("clearSession resets accessToken, isAuthenticated, user, and expiresAt", () => {
    const token = makeToken({ sub: "u", role: "admin", exp: 1 });
    useAuthStore.getState().setAccessToken(token);

    useAuthStore.getState().clearSession();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.expiresAt).toBeNull();
  });

  describe("hasRole", () => {
    it("returns false when logged out", () => {
      expect(useAuthStore.getState().hasRole(["admin", "super_admin"])).toBe(false);
    });

    it("returns true when the user's role is in the allowed list", () => {
      const token = makeToken({ sub: "u", role: "admin", exp: 1 });
      useAuthStore.getState().setAccessToken(token);

      expect(useAuthStore.getState().hasRole(["admin", "super_admin"])).toBe(true);
    });

    it("returns false when the user's role is not in the allowed list", () => {
      const token = makeToken({ sub: "u", role: "user", exp: 1 });
      useAuthStore.getState().setAccessToken(token);

      expect(useAuthStore.getState().hasRole(["admin", "super_admin"])).toBe(false);
    });
  });
});
