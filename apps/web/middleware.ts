import { type NextRequest, NextResponse } from "next/server";

/**
 * Protected route middleware — Document 2 §5.2: "middleware.ts — Next.js
 * middleware — route protection." Phase 2 scope: gates the (app) route
 * group behind a session check.
 *
 * IMPORTANT DISCLOSED LIMITATION: this checks for the presence of a
 * refresh-token cookie set by the BFF — but per lib/auth-api.ts's own
 * documented interim (the BFF cookie-setting route isn't built yet in
 * Phase 2, tokens currently return directly in the JSON response body),
 * this cookie does not yet actually get set anywhere. This middleware is
 * therefore written correctly against the TARGET architecture (Document 3
 * §7.4) but is not yet exercised end-to-end — real route protection
 * currently happens client-side via useAuthStore's isAuthenticated flag
 * (see features/auth's page-level guards), which is view-layer-only
 * protection, not a true server-enforced boundary. This gap is called out
 * explicitly in the Phase 2 verification report rather than silently
 * left unflagged — closing it requires the BFF cookie route mentioned above.
 */
const SESSION_COOKIE_NAME = "investiq_refresh_token";
const PROTECTED_PATH_PREFIX = "/dashboard";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith(PROTECTED_PATH_PREFIX)) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectTo", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
