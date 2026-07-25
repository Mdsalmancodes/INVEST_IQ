"""SecurityHeadersMiddleware — Phase 8. Applies the general-purpose
security headers from docs/architecture/06-security-testing-strategy.md
§15.5 to every response.

Document 06's §15.5 explicitly scopes the full header set (including the
Spline/R3F-specific Content-Security-Policy directives) to "enforced at
BFF/Next.js middleware level" — i.e. apps/web/middleware.ts is §15.5's
primary specified location for CSP, since CSP's script-src/connect-src/
frame-src directives are inherently about what the BROWSER is allowed to
load, a decision that belongs with the app actually serving HTML/JS, not
a backend JSON API. core-api has no CSP-relevant surface (it never serves
HTML), so this middleware deliberately omits Content-Security-Policy and
carries only the headers that are meaningful for a JSON API and provide
genuine defense-in-depth regardless of which service enforces them:
HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and
Permissions-Policy — copied from §15.5's exact specified values.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers[name] = value
        return response
