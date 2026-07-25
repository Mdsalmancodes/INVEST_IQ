"use client";

import type { ReactNode } from "react";

import { useAuthStore } from "../../../store/auth-store";
import type { Role } from "../../../store/types";

export interface RequireRoleProps {
  /** Roles allowed to see `children`. Matches core-api's require_role(allowed_roles) convention (presentation/dependencies/rbac.py) — pass the same role set used to gate the corresponding API call. */
  allowedRoles: Role[];
  children: ReactNode;
  /** Rendered instead of `children` when the current user's role is not in `allowedRoles` (or the user is logged out). Defaults to rendering nothing. */
  fallback?: ReactNode;
}

/**
 * RequireRole — Phase 8 Permission Guard.
 *
 * Conditionally renders `children` based on the current user's role
 * (decoded client-side from the access token via useAuthStore's `user`
 * field — see lib/jwt.ts and store/auth-store.ts). Used to hide
 * admin-only controls (e.g. the AI dashboard's model train/retrain/
 * delete actions) from Basic/Premium users so they never see UI for
 * actions they cannot perform.
 *
 * SECURITY NOTE: this is a UX convenience, not an authorization
 * boundary. Hiding a button does not stop a determined client from
 * calling the underlying API directly — the real authorization check is
 * core-api's require_role dependency (presentation/dependencies/
 * rbac.py), enforced server-side on every request to an admin-gated
 * endpoint (e.g. the AI proxy's /api/v1/ai/models/{status,train,
 * retrain,{id}} routes — see src/presentation/routers/ai_proxy_router.py).
 * This component exists purely so legitimate users see a UI that matches
 * what they're actually permitted to do.
 */
export function RequireRole({ allowedRoles, children, fallback = null }: RequireRoleProps) {
  const hasRole = useAuthStore((state) => state.hasRole);

  if (!hasRole(allowedRoles)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

/** Convenience alias matching this codebase's admin-tier convention (ADMIN + SUPER_ADMIN treated as "Admin" in user-facing terminology — see docs/phase-8/implementation-summary.md). */
export const ADMIN_ROLES: Role[] = ["admin", "super_admin"];
