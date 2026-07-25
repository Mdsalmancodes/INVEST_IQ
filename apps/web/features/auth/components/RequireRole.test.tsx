import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "../../../store/auth-store";
import { ADMIN_ROLES, RequireRole } from "./RequireRole";

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(role: string): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64UrlEncode(JSON.stringify({ sub: "u", role, exp: Math.floor(Date.now() / 1000) + 900 }));
  return `${header}.${body}.fake-signature`;
}

describe("RequireRole", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
  });

  it("renders children when the user's role is allowed", () => {
    useAuthStore.getState().setAccessToken(makeToken("admin"));

    render(
      <RequireRole allowedRoles={ADMIN_ROLES}>
        <p>Admin-only content</p>
      </RequireRole>
    );

    expect(screen.getByText("Admin-only content")).toBeInTheDocument();
  });

  it("renders nothing by default when the user's role is not allowed", () => {
    useAuthStore.getState().setAccessToken(makeToken("user"));

    render(
      <RequireRole allowedRoles={ADMIN_ROLES}>
        <p>Admin-only content</p>
      </RequireRole>
    );

    expect(screen.queryByText("Admin-only content")).not.toBeInTheDocument();
  });

  it("renders the fallback when provided and the role is not allowed", () => {
    useAuthStore.getState().setAccessToken(makeToken("pro_user"));

    render(
      <RequireRole allowedRoles={ADMIN_ROLES} fallback={<p>Not permitted</p>}>
        <p>Admin-only content</p>
      </RequireRole>
    );

    expect(screen.queryByText("Admin-only content")).not.toBeInTheDocument();
    expect(screen.getByText("Not permitted")).toBeInTheDocument();
  });

  it("renders nothing when logged out entirely", () => {
    render(
      <RequireRole allowedRoles={ADMIN_ROLES}>
        <p>Admin-only content</p>
      </RequireRole>
    );

    expect(screen.queryByText("Admin-only content")).not.toBeInTheDocument();
  });

  it("treats SUPER_ADMIN as an admin-tier role via the ADMIN_ROLES convenience export", () => {
    useAuthStore.getState().setAccessToken(makeToken("super_admin"));

    render(
      <RequireRole allowedRoles={ADMIN_ROLES}>
        <p>Admin-only content</p>
      </RequireRole>
    );

    expect(screen.getByText("Admin-only content")).toBeInTheDocument();
  });
});
