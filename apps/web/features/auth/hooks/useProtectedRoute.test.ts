import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../../store/auth-store";
import { useProtectedRoute } from "./useProtectedRoute";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(role: string): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64UrlEncode(
    JSON.stringify({ sub: "u", role, exp: Math.floor(Date.now() / 1000) + 900 })
  );
  return `${header}.${body}.fake-signature`;
}

describe("useProtectedRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearSession();
  });

  it("redirects to /login with the given redirectPath when unauthenticated", () => {
    const { result } = renderHook(() =>
      useProtectedRoute({ redirectPath: "%2Fdashboard%2Fadmin" })
    );

    expect(result.current.canRender).toBe(false);
    expect(replaceMock).toHaveBeenCalledWith("/login?redirectTo=%2Fdashboard%2Fadmin");
  });

  it("allows rendering when authenticated and no role is required", () => {
    useAuthStore.getState().setAccessToken(makeToken("user"));

    const { result } = renderHook(() => useProtectedRoute({ redirectPath: "%2Fdashboard" }));

    expect(result.current.canRender).toBe(true);
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("redirects to /dashboard (not /login) when authenticated but missing a required role", () => {
    useAuthStore.getState().setAccessToken(makeToken("user"));

    const { result } = renderHook(() =>
      useProtectedRoute({ redirectPath: "%2Fdashboard%2Fadmin", requiredRoles: ["admin", "super_admin"] })
    );

    expect(result.current.canRender).toBe(false);
    expect(replaceMock).toHaveBeenCalledWith("/dashboard");
  });

  it("allows rendering when authenticated and the role requirement is satisfied", () => {
    useAuthStore.getState().setAccessToken(makeToken("admin"));

    const { result } = renderHook(() =>
      useProtectedRoute({ redirectPath: "%2Fdashboard%2Fadmin", requiredRoles: ["admin", "super_admin"] })
    );

    expect(result.current.canRender).toBe(true);
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
