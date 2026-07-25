"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";

import { authApi } from "../../../lib/auth-api";
import { useAuthStore } from "../../../store/auth-store";

/**
 * How long before the access token's natural expiry (core-api's
 * jwt_access_token_ttl_minutes=15, src/config.py) a proactive refresh is
 * attempted, so a user is never interrupted by a token expiring mid-use.
 * 2 minutes leaves ample margin over normal network latency while still
 * being well inside the 15-minute window.
 */
const REFRESH_LEAD_TIME_MS = 2 * 60 * 1000;

/**
 * Idle timeout — Document 3 §7.4-style session management: if the user
 * performs no tracked activity for this long, the session is cleared and
 * they are redirected to /login, independent of whether the access token
 * itself is still technically valid. 30 minutes is a reasonable default
 * for a financial dashboard (balances security against not logging out
 * an actively-reading-but-not-clicking user too aggressively) — no
 * existing config/doc value was found for this specific number, so this
 * is a disclosed, sensible default rather than a value taken from a
 * spec.
 */
const IDLE_TIMEOUT_MS = 30 * 60 * 1000;

const ACTIVITY_EVENTS = ["mousedown", "keydown", "scroll", "touchstart"] as const;

/**
 * useSessionManager — Phase 8 Session Management, Auto Logout, and
 * Refresh Token Handling.
 *
 * Mount once near the root of the authenticated app (e.g. a dashboard
 * layout, or each protected page until a shared layout exists — see
 * this hook's call sites). While a session is active it:
 *
 * 1. Proactively refreshes the access token shortly before it expires
 *    (using useAuthStore's `expiresAt`, populated from the token's own
 *    `exp` claim — see lib/jwt.ts/store/auth-store.ts), calling
 *    authApi.refreshAccessToken() and feeding the rotated token back
 *    into the store via setAccessToken. If the refresh call itself
 *    fails (e.g. the refresh token was revoked/expired), the session is
 *    cleared and the user is sent to /login — this is the correct
 *    reactive fallback for a refresh failure, distinct from proactive
 *    refresh succeeding.
 * 2. Tracks basic user activity (mouse/keyboard/scroll/touch) and clears
 *    the session + redirects to /login after IDLE_TIMEOUT_MS of no
 *    activity, regardless of whether the access token is still valid.
 *
 * Does nothing while logged out (isAuthenticated=false) — every timer
 * and listener is torn down on logout/unmount.
 */
export function useSessionManager(): void {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const expiresAt = useAuthStore((state) => state.expiresAt);
  const accessToken = useAuthStore((state) => state.accessToken);
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const clearSession = useAuthStore((state) => state.clearSession);

  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const logoutAndRedirect = useCallback(() => {
    const currentToken = useAuthStore.getState().accessToken;
    clearSession();
    router.replace("/login");
    if (currentToken) {
      // Best-effort — the session is already cleared client-side
      // regardless of whether this network call succeeds, matching the
      // principle that logout must never be blocked by a flaky network.
      void authApi.logoutCurrentSession(currentToken).catch(() => {
        // Intentionally swallowed: the client-side session is already
        // gone; a failed server-side logout call just means the access
        // token isn't blacklisted server-side and will simply expire
        // naturally within its remaining TTL (at most 15 minutes).
      });
    }
  }, [clearSession, router]);

  // --- Idle timeout ---------------------------------------------------
  useEffect(() => {
    if (!isAuthenticated) {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      return;
    }

    const resetIdleTimer = () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(logoutAndRedirect, IDLE_TIMEOUT_MS);
    };

    resetIdleTimer();
    for (const eventName of ACTIVITY_EVENTS) {
      window.addEventListener(eventName, resetIdleTimer);
    }

    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      for (const eventName of ACTIVITY_EVENTS) {
        window.removeEventListener(eventName, resetIdleTimer);
      }
    };
  }, [isAuthenticated, logoutAndRedirect]);

  // --- Proactive token refresh -----------------------------------------
  useEffect(() => {
    if (!isAuthenticated || expiresAt === null) {
      return;
    }

    const msUntilRefresh = expiresAt - REFRESH_LEAD_TIME_MS - Date.now();

    const performRefresh = async () => {
      try {
        const result = await authApi.refreshAccessToken();
        setAccessToken(result.access_token);
      } catch {
        logoutAndRedirect();
      }
    };

    // If the token is already past its refresh point (e.g. the tab was
    // backgrounded), refresh immediately rather than scheduling a
    // negative-delay timer.
    const refreshTimer = setTimeout(performRefresh, Math.max(msUntilRefresh, 0));

    return () => clearTimeout(refreshTimer);
    // accessToken is intentionally included so a token rotation
    // (new expiresAt) re-schedules this effect against the NEW token's
    // expiry rather than continuing to count down against a stale one.
  }, [isAuthenticated, expiresAt, accessToken, setAccessToken, logoutAndRedirect]);
}
