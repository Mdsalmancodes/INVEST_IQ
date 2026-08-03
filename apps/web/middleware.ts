import { type NextRequest, NextResponse } from "next/server";

/**
 * Protected route middleware — Document 2 §5.2: "middleware.ts — Next.js
 * middleware — route protection." Phase 2 scope: gates the (app) route
 * group behind a session check.
 *
 * This checks for the presence of a refresh-token cookie set by the BFF
 * (app/api/bff/login/route.ts, app/api/bff/refresh/route.ts) — the gate
 * logic below was always written correctly against the TARGET
 * architecture (Document 3 §7.4) and is UNCHANGED by the fix described
 * below; what was missing was the BFF itself actually setting that
 * cookie. lib/auth-api.ts's login()/refreshAccessToken()/
 * logoutCurrentSession() now call those BFF routes (same-origin, so the
 * httpOnly cookie is attached/received automatically) instead of calling
 * core-api's /auth/{login,refresh,logout} directly — the raw refresh
 * token is now handled exclusively server-side inside the BFF route
 * handlers and never reaches client JS at all, matching this
 * architecture's original XSS-mitigation rationale exactly (previously,
 * before this fix, an in-memory JS variable held it as a disclosed,
 * narrower interim — see git history for that prior state).
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
 *
 * Post-launch fix #1: the Phase 8 CSP above was strict enough to also
 * block `next dev`'s own inline bootstrap scripts and eval()-based HMR
 * runtime, which silently prevented any client-only code (the landing
 * page's React Three Fiber canvas, GSAP tweens, Framer Motion
 * animations) from ever mounting in local development — confirmed via a
 * headless-browser console capture showing repeated CSP `script-src`
 * violations. Fixed by branching the policy on NODE_ENV: the production
 * policy is byte-for-byte unchanged; a development-only variant
 * additionally allows 'unsafe-inline'/'unsafe-eval' in script-src only.
 *
 * Post-launch fix #2: the SAME CSP's `connect-src` directive only ever
 * listed the production placeholder API domain (https://api.investiq.app)
 * — never core-api's real local dev address (http://localhost:8001) —
 * which meant every single fetch() call this frontend makes to core-api
 * (register, login, every dashboard API call) was silently blocked by
 * the browser itself before the request ever left the page. This
 * surfaced as registration (and everything else) failing with a generic
 * "Something went wrong" message with no backend-side error, since
 * curl-based backend testing never exercises the browser's CSP
 * enforcement and therefore could never reproduce it — only a real
 * browser network trace (`Refused to connect to 'http://localhost:8001/
 * ...' because it violates the following Content Security Policy
 * directive: "connect-src"`) surfaced the actual failure point. Fixed by
 * adding http://localhost:8001 and ws://localhost:8001 to the
 * DEVELOPMENT_CONTENT_SECURITY_POLICY's connect-src only — production's
 * connect-src is unchanged (it should point at the real deployed API
 * domain once one exists, not localhost).
 */
const SESSION_COOKIE_NAME = "investiq_refresh_token";
const PROTECTED_PATH_PREFIX = "/dashboard";

// Production CSP — unchanged from Phase 8. `script-src` intentionally has
// no 'unsafe-inline'/'unsafe-eval': Next.js's PRODUCTION build (next build
// && next start) does not need either (no eval-based HMR, no inline
// bootstrap scripts), so this stays maximally strict for real deployments.
const PRODUCTION_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "connect-src 'self' https://api.investiq.app wss://api.investiq.app",
  "worker-src 'self' blob:",
  "img-src 'self' data: https://*.investiq-cdn.app",
  "style-src 'self' 'unsafe-inline'",
].join("; ");

// Development-only CSP — identical to the production policy except:
// (a) `script-src` additionally allows 'unsafe-inline' and 'unsafe-eval'
//     (next dev's inline hydration bootstrap scripts and eval()-based
//     HMR/Fast Refresh runtime require both);
// (b) `connect-src` additionally allows http://localhost:8001 and
//     ws://localhost:8001 — core-api's real local dev address. The
//     production connect-src only ever listed the production placeholder
//     domain (https://api.investiq.app), which does not resolve locally,
//     so every fetch() call the frontend makes to core-api (register,
//     login, every other API call) was being silently blocked by the
//     browser's own CSP enforcement — confirmed via a headless-browser
//     console capture: "Refused to connect to 'http://localhost:8001/
//     api/v1/auth/register' because it violates the following Content
//     Security Policy directive: connect-src". This is why registration
//     (and every other API call) appeared to fail with a generic
//     "Something went wrong" — the request never left the browser, so
//     curl-based backend testing alone could never reproduce it.
// No other directive is relaxed — worker-src/img-src/style-src stay
// identical to production.
const DEVELOPMENT_CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'",
  "connect-src 'self' http://localhost:8001 ws://localhost:8001 https://api.investiq.app wss://api.investiq.app",
  "worker-src 'self' blob:",
  "img-src 'self' data: https://*.investiq-cdn.app",
  "style-src 'self' 'unsafe-inline'",
].join("; ");

const CONTENT_SECURITY_POLICY =
  process.env.NODE_ENV === "development"
    ? DEVELOPMENT_CONTENT_SECURITY_POLICY
    : PRODUCTION_CONTENT_SECURITY_POLICY;

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
