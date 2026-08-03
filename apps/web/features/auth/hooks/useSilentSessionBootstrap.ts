"use client";

import { useEffect, useRef } from "react";

import { authApi } from "../../../lib/auth-api";
import { useAuthStore } from "../../../store/auth-store";

/**
 * useSilentSessionBootstrap — Document 3 §7.4's "silent-refresh-on-load"
 * flow, referenced explicitly in store/auth-store.ts's own docstring:
 * "a silent-refresh-on-load flow, using the httpOnly refresh cookie, is
 * how a real session survives a reload." useAuthStore's access token is
 * intentionally in-memory-only and is therefore always empty immediately
 * after a fresh page load/reload — this hook is what repopulates it
 * (without any user interaction) by calling the BFF's /api/bff/refresh
 * route once on mount, which succeeds silently if the httpOnly refresh
 * cookie is still present/valid, or fails harmlessly (leaving the user
 * logged out, exactly as before this hook existed) if it is not.
 *
 * Mounted once near the root (see app/providers.tsx) so every page —
 * including a hard reload of a /dashboard/* route — gets a chance to
 * restore its session before any page-level `if (!isAuthenticated)
 * redirect` guard runs. Runs at most once per full page load (the ref
 * guard prevents a duplicate call from React 18 Strict Mode's
 * intentional double-invocation of effects in development).
 */
export function useSilentSessionBootstrap(): void {
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const finishBootstrapping = useAuthStore((state) => state.finishBootstrapping);
  const hasAttempted = useRef(false);

  useEffect(() => {
    if (hasAttempted.current) return;
    hasAttempted.current = true;

    authApi
      .refreshAccessToken()
      .then((result) => {
        setAccessToken(result.access_token);
      })
      .catch(() => {
        // No valid httpOnly refresh cookie (never logged in, already
        // logged out, or the refresh token expired/was revoked) — this
        // is the normal, expected outcome for a logged-out visitor, not
        // an error to surface. The user simply stays logged out, exactly
        // as before this hook existed.
        finishBootstrapping();
      });
  }, [setAccessToken, finishBootstrapping]);
}
