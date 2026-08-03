import { NextResponse } from "next/server";

/**
 * BFF login route — Document 3 §7.4's target architecture, step 4:
 * "Next.js BFF sets Refresh Token as httpOnly+secure+sameSite=strict
 * cookie." This is the missing piece middleware.ts's own docstring
 * names as the reason its dashboard gate was written against the
 * TARGET architecture but not yet exercised end-to-end — this route is
 * that missing piece.
 *
 * Forwards the login request to core-api unchanged, then splits the
 * response: the refresh_token is set as an httpOnly/secure/sameSite=strict
 * cookie (never touches client JS, matching Document 3 §7.4's XSS
 * rationale), while only the access_token is returned in the JSON body
 * for useAuthStore to hold in memory (unchanged behavior on the client
 * side — see store/auth-store.ts's own docstring on why the access token
 * stays in-memory-only).
 */

const CORE_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const REFRESH_TOKEN_COOKIE_NAME = "investiq_refresh_token";
// Matches core-api's own jwt_refresh_token_ttl_days=30 default (src/config.py)
// — the cookie's own expiry should not outlive the token it carries.
const REFRESH_TOKEN_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();

  const coreApiResponse = await fetch(`${CORE_API_BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });

  const responseBody = await coreApiResponse.text();

  if (!coreApiResponse.ok) {
    // Forward core-api's error shape/status unchanged — the BFF is a
    // transparent proxy on the error path, same principle
    // HttpAiServiceClient's own docstring uses for core-api<->ai-service.
    return new NextResponse(responseBody, {
      status: coreApiResponse.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const parsed = JSON.parse(responseBody) as {
    access_token: string;
    refresh_token: string;
    token_type: string;
  };

  const response = NextResponse.json({
    access_token: parsed.access_token,
    token_type: parsed.token_type,
  });

  response.cookies.set(REFRESH_TOKEN_COOKIE_NAME, parsed.refresh_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV !== "development",
    sameSite: "strict",
    path: "/",
    maxAge: REFRESH_TOKEN_COOKIE_MAX_AGE_SECONDS,
  });

  return response;
}
