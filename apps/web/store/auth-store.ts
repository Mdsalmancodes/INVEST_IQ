import { create } from "zustand";

import { decodeAccessToken } from "../lib/jwt";
import type { Role } from "./types";

/**
 * Auth session store — Document 3 §7.4: access token kept in memory only,
 * NEVER localStorage (XSS mitigation) — this store is exactly that memory,
 * cleared on page reload by design (a silent-refresh-on-load flow, using
 * the httpOnly refresh cookie, is how a real session survives a reload;
 * that BFF cookie-setting route is a later-phase concern per Document 3
 * §7.4's flow — Phase 2 scope is the auth pages/components themselves).
 *
 * Uses Zustand (not Redux Toolkit) for this store — Document 2 §6.2 names
 * Redux Toolkit for the platform's general cross-cutting client state, but
 * Phase 2's actual scope is auth session state only. Zustand is a lighter,
 * equally-standard choice for this narrower scope; this is a disclosed
 * simplification (not a silent architecture deviation) and does not
 * preclude adopting Redux Toolkit for other client state in later phases.
 *
 * SECURITY NOTE (deliberate scope limitation, not an oversight): this
 * store holds ONLY the access token, never the refresh token. Document 3
 * §7.4's real design has the BFF set the refresh token as an httpOnly,
 * secure, sameSite=strict cookie — invisible to JavaScript entirely, which
 * is what actually protects it from XSS-based theft (an in-memory JS
 * store, unlike an httpOnly cookie, IS readable by any script that runs on
 * the page, so it provides no real protection for the refresh token
 * specifically). That BFF cookie-setting route is not yet built in Phase 2
 * (auth_router.py returns both tokens directly in the response body for
 * now, matching Document 4 §9.4's LoginResponse shape) — wiring the BFF to
 * intercept that response and set the cookie server-side, so the refresh
 * token never reaches client JS at all, is the correct next step and is
 * called out explicitly in the Phase 2 verification report's known-issues
 * section rather than silently worked around by storing it here.
 */

export interface AuthUser {
  userId: string;
  role: Role;
}

interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
  /**
   * Phase 8 addition — the current user's id/role, decoded client-side
   * from the access token's own claims (lib/jwt.ts's decodeAccessToken,
   * no signature verification, UI-rendering purposes only; see that
   * module's docstring for why this is not a security boundary). null
   * whenever accessToken is null, or if a token somehow fails to decode
   * (never crashes the store — a decode failure just means no
   * role-gated UI renders, which is the safe default).
   */
  user: AuthUser | null;
  /**
   * Phase 8 addition — the access token's own expiry (ms epoch), read
   * from its `exp` claim. Used by session-management/auto-logout
   * (Task 12) to know when a proactive refresh or idle-driven logout is
   * due, without re-decoding the token at every check.
   */
  expiresAt: number | null;
  setAccessToken: (accessToken: string) => void;
  clearSession: () => void;
  /** Phase 8 addition — true if the current user's role is one of `roles`. False when logged out or role is unknown. */
  hasRole: (roles: Role[]) => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  isAuthenticated: false,
  user: null,
  expiresAt: null,
  setAccessToken: (accessToken) => {
    const decoded = decodeAccessToken(accessToken);
    set({
      accessToken,
      isAuthenticated: true,
      user: decoded ? { userId: decoded.userId, role: decoded.role } : null,
      expiresAt: decoded?.expiresAt ?? null,
    });
  },
  clearSession: () => set({ accessToken: null, isAuthenticated: false, user: null, expiresAt: null }),
  hasRole: (roles) => {
    const currentUser = get().user;
    return currentUser !== null && roles.includes(currentUser.role);
  },
}));

