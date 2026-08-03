import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * BFF refresh route — Document 3 §7.4 step 5: "On Access Token expiry,
 * client calls /auth/refresh silently, BFF forwards the httpOnly refresh
 * cookie to core-api, which validates it against the stored hash,
 * rotates it (issues new refresh token, invalidates old one — refresh
 * token rotation prevents replay), and returns new Access Token."
 *
 * The raw refresh token never reaches client JS in either direction:
 * read here server-side from the httpOnly cookie (never exposed via
 * request.json()), sent to core-api, and the ROTATED replacement is
 * written back into the same httpOnly cookie — only the new access
 * token is returned in the JSON body.
 */

const CORE_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const REFRESH_TOKEN_COOKIE_NAME = "investiq_refresh_token";
const REFRESH_TOKEN_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

export async function POST(): Promise<NextResponse> {
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get(REFRESH_TOKEN_COOKIE_NAME)?.value;

  if (!refreshToken) {
    return NextResponse.json(
      {
        success: false,
        error: { code: "NO_REFRESH_TOKEN", message: "No active session to refresh" },
      },
      { status: 401 }
    );
  }

  const coreApiResponse = await fetch(`${CORE_API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const responseBody = await coreApiResponse.text();

  if (!coreApiResponse.ok) {
    const response = new NextResponse(responseBody, {
      status: coreApiResponse.status,
      headers: { "Content-Type": "application/json" },
    });
    // A rejected refresh token (expired/already-rotated/reuse-detected)
    // can never become valid again — clear the now-useless cookie rather
    // than leaving a dead value sitting in the browser.
    response.cookies.delete(REFRESH_TOKEN_COOKIE_NAME);
    return response;
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
