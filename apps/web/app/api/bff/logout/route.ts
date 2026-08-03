import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * BFF logout route — Document 3 §7.4 step 6: "Logout: refresh token is
 * deleted from Postgres+Redis, cookie cleared."
 *
 * core-api's own POST /api/v1/auth/logout (Phase 8) requires BOTH the
 * refresh token (body) AND a valid bearer access token (so it can
 * blacklist the access token's jti too, not just delete the refresh
 * token — see auth_router.py's logout() docstring). The access token
 * is forwarded from this request's own Authorization header (the
 * client still holds it in memory per useAuthStore, unchanged); the
 * refresh token is read server-side from the httpOnly cookie, never
 * exposed to client JS.
 */

const CORE_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const REFRESH_TOKEN_COOKIE_NAME = "investiq_refresh_token";

export async function POST(request: Request): Promise<NextResponse> {
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get(REFRESH_TOKEN_COOKIE_NAME)?.value;
  const authorizationHeader = request.headers.get("authorization");

  // Best-effort, matching the client's own existing
  // logoutCurrentSession() semantics (features/../lib/auth-api.ts): the
  // local session must be clearable even if the server-side call fails
  // (e.g. the access token already expired) — so any core-api failure
  // here still results in the cookie being cleared below, not an error
  // surfaced to the caller.
  if (refreshToken && authorizationHeader) {
    try {
      await fetch(`${CORE_API_BASE_URL}/api/v1/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: authorizationHeader,
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // Network failure calling core-api — still clear the cookie below.
    }
  }

  const response = new NextResponse(null, { status: 204 });
  response.cookies.delete(REFRESH_TOKEN_COOKIE_NAME);
  return response;
}
