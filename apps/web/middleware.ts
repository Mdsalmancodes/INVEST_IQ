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
 *
 * Phase 8 addition: security headers (docs/architecture/06-security-
 * testing-strategy.md §15.5) are applied here, to EVERY response — this
 * is §15.5's own explicitly specified primary location for the full
 * header set including Content-Security-Policy, since CSP's script-src/
 * connect-src/frame-src directives describe what the BROWSER is allowed
 * to load for pages this app itself serves, a decision that belongs with
 * the Next.js app, not the backend JSON API (core-api's own
 * SecurityHeadersMiddleware carries the non-CSP headers as backend-side
 * defense-in-depth, but omits CSP for exactly this reason — see that
 * middleware's module docstring).
 */
const SESSION_COOKIE_NAME = "investiq_refresh_token";
const PROTECTED_PATH_PREFIX = "/dashboard";

const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "connect-src 'self' https://api.investiq.app wss://api.investiq.app https://*.spline.design",
  "frame-src 'self' https://my.spline.design",
  "worker-src 'self' blob:",
  "img-src 'self' data: https://*.investiq-cdn.app",
  "style-src 'self' 'unsafe-inline'",
].join("; ");

function applySecurityHeaders(response: NextResponse): NextResponse {
  response.headers.set("Content-Security-Policy", CONTENT_SECURITY_POLICY);
  response.headers.set(
    "Strict-Transport-Security",
    "max-age=63072000; includeSubDomains; preload"
  );
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "geolocation=(), microphone=(), camera=()");
  return response;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!pathname.startsWith(PROTECTED_PATH_PREFIX)) {
    return applySecurityHeaders(NextResponse.next());
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectTo", pathname);
    return applySecurityHeaders(NextResponse.redirect(loginUrl));
  }

  return applySecurityHeaders(NextResponse.next());
}

export const config = {
  // Broadened from the Phase 2 dashboard-only matcher — security headers
  // (Phase 8) must apply to every route, not just the auth-gated ones;
  // the auth-gate logic itself remains scoped to PROTECTED_PATH_PREFIX
  // inside the function body, unchanged from Phase 2. Excludes Next.js
  // internals/static assets, matching the framework's own documented
  // recommended matcher pattern for "run on everything except these."
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
