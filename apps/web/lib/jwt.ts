/**
 * Minimal client-side JWT payload decoder — Phase 8 (Permission Guards).
 *
 * This deliberately does NOT verify the token's signature. Signature
 * verification is core-api's job (src/infrastructure/security/
 * jwt_provider.py's JwtProvider.verify_access_token, kid-based, run
 * server-side on every authenticated request) — the actual authorization
 * boundary is enforced there and in the RBAC dependency
 * (presentation/dependencies/rbac.py's require_role), never in the
 * browser. This decoder exists ONLY so the UI can read its own claims
 * (role, user id, expiry) to decide what to *render* — e.g. hiding an
 * "Admin" section from a Basic/Premium user. Hiding a button is a UX
 * nicety, not a security control; a malicious client could forge/ignore
 * this decode entirely and still be stopped by the real server-side
 * checks. No new dependency (e.g. jwt-decode) was added for this single
 * base64url-decode operation — matching this codebase's preference for
 * small purpose-built helpers over pulling in a package for one call.
 */

import type { Role } from "../store/types";

export interface DecodedAccessToken {
  userId: string;
  role: Role;
  expiresAt: number | null;
}

function base64UrlDecode(segment: string): string {
  const normalized = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  // atob is available in both browser and jsdom (Vitest) environments.
  return atob(padded);
}

/**
 * Decodes a JWT's payload segment. Returns null if the token is
 * malformed or missing expected claims — callers must treat a null
 * result as "no role information available" (e.g. render nothing
 * role-gated) rather than throwing, since a decode failure must never
 * crash the UI.
 */
export function decodeAccessToken(token: string): DecodedAccessToken | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payloadSegment = parts[1];
    if (!payloadSegment) return null;

    const payload = JSON.parse(base64UrlDecode(payloadSegment)) as Record<string, unknown>;

    const userId = payload.sub ?? payload.user_id;
    const role = payload.role;

    if (typeof userId !== "string" || typeof role !== "string") {
      return null;
    }

    const validRoles: Role[] = ["user", "pro_user", "admin", "super_admin"];
    if (!validRoles.includes(role as Role)) {
      return null;
    }

    const exp = payload.exp;
    const expiresAt = typeof exp === "number" ? exp * 1000 : null;

    return { userId, role: role as Role, expiresAt };
  } catch {
    return null;
  }
}
