"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuthStore } from "../../../store/auth-store";
import type { Role } from "../../../store/types";

export interface UseProtectedRouteOptions {
  /** Current path, used to build the post-login redirectTo query param (must be URL-encoded by the caller, matching every existing dashboard page's own literal string, e.g. "%2Fdashboard%2Fwatchlists"). */
  redirectPath: string;
  /** If provided, the route additionally requires the current user's role to be one of these — an authenticated user with the wrong role is redirected to /dashboard (not /login, since they ARE logged in, just not permitted here) rather than being shown the page. */
  requiredRoles?: Role[];
}

export interface UseProtectedRouteResult {
  /** True once the route's guard conditions are satisfied and the page's real content should render. False while a redirect is pending/in-flight — callers should render null (or a loading state) in that case, matching every existing dashboard page's `if (!isAuthenticated) return null;` convention. */
  canRender: boolean;
}

/**
 * useProtectedRoute — Phase 8 formalization of the client-side
 * route-guard pattern already used identically across every existing
 * /dashboard/* page (app/dashboard/{watchlists,portfolios,alerts,
 * notifications,ai}/page.tsx and their [id] variants) — each currently
 * duplicates the same "redirect to /login if !isAuthenticated" effect
 * inline. Per this phase's "do not modify completed features" rule,
 * those existing pages are NOT refactored to use this hook (that would
 * be a cosmetic rewrite of completed Phase 3/5/7 code) — this hook is
 * new, additive infrastructure for pages built from Phase 8 onward
 * (e.g. any new admin-only route/section), and additionally supports an
 * optional role requirement, which no existing page needed until now.
 */
export function useProtectedRoute({
  redirectPath,
  requiredRoles,
}: UseProtectedRouteOptions): UseProtectedRouteResult {
  const router = useRouter();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const hasRole = useAuthStore((state) => state.hasRole);

  const hasRequiredRole = !requiredRoles || hasRole(requiredRoles);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace(`/login?redirectTo=${redirectPath}`);
      return;
    }
    if (!hasRequiredRole) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, hasRequiredRole, redirectPath, router]);

  return { canRender: isAuthenticated && hasRequiredRole };
}
