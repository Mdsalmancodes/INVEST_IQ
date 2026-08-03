/**
 * Typed API client for auth endpoints — Document 2 §5.2's "typed fetch
 * wrapper, interceptors, error mapping" (lib/api-client.ts pattern),
 * scoped to auth for Phase 2. Talks to the BFF route handlers (not
 * core-api directly from the browser) — Document 3 §7.3.
 *
 * REFRESH TOKEN HANDLING: Document 3 §7.4's target design — the Next.js
 * BFF intercepts /login and /refresh responses, strips the refresh token
 * out, and sets it as an httpOnly/secure/sameSite=strict cookie, invisible
 * to JS entirely — is now fully implemented via app/api/bff/{login,
 * refresh,logout}/route.ts. This module calls THOSE routes (same-origin,
 * so the browser attaches/receives the httpOnly cookie automatically —
 * no `refreshTokenInMemory` variable, no explicit refresh_token ever
 * appears in this file's requests or responses) rather than calling
 * core-api's /auth/{login,refresh,logout} directly. core-api's raw
 * refresh_token value is now handled exclusively server-side, inside the
 * BFF route handlers — it is never present in any browser-visible
 * JavaScript value, closing the gap the module docstring here previously
 * disclosed as an interim (in-memory-variable) approximation.
 */

export interface ApiErrorPayload {
  success: false;
  error: { code: string; message: string; details?: Record<string, unknown> };
  meta: { timestamp?: string; requestId?: string };
}

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

async function request<TResponse>(
  path: string,
  options: RequestInit & { accessToken?: string } = {}
): Promise<TResponse> {
  const { accessToken, headers, ...rest } = options;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const body = await response.json();

  if (!response.ok) {
    // core-api's error shape is FastAPI's default {"detail": ...} for
    // HTTPException, or the structured {"success":false,"error":{...}}
    // envelope for the catch-all handler (Document 5 §14.3) — both are
    // handled here so callers get a consistent ApiError regardless.
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : (body as ApiErrorPayload)?.error?.message ?? "Request failed";
    const code = (body as ApiErrorPayload)?.error?.code ?? "REQUEST_FAILED";
    throw new ApiError(code, detail, response.status);
  }

  return body as TResponse;
}

/**
 * Same-origin requests to this Next.js app's own /api/bff/* Route
 * Handlers — deliberately NOT going through `request()`/API_BASE_URL
 * (those target core-api directly). `credentials: "include"` ensures the
 * httpOnly refresh-token cookie is sent/received even though these calls
 * originate from client components, matching how the browser already
 * automatically attaches cookies to same-origin requests by default —
 * stated explicitly here rather than relying on the implicit default.
 */
async function bffRequest<TResponse>(
  path: string,
  options: RequestInit & { accessToken?: string } = {}
): Promise<TResponse> {
  const { accessToken, headers, ...rest } = options;
  const response = await fetch(path, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
  });

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const body = await response.json();

  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : (body as ApiErrorPayload)?.error?.message ?? "Request failed";
    const code = (body as ApiErrorPayload)?.error?.code ?? "REQUEST_FAILED";
    throw new ApiError(code, detail, response.status);
  }

  return body as TResponse;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterResponse {
  user_id: string;
  email: string;
  message: string;
}

export interface MessageResponse {
  message: string;
}

export const authApi = {
  register: (payload: { email: string; password: string; full_name: string }) =>
    request<RegisterResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  login: (payload: { email: string; password: string }) =>
    bffRequest<LoginResponse>("/api/bff/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  refreshAccessToken: () =>
    bffRequest<LoginResponse>("/api/bff/refresh", { method: "POST" }),

  logoutCurrentSession: async (accessToken: string) => {
    // Phase 8: core-api's POST /api/v1/auth/logout requires
    // authentication (it needs the presented access token's jti to add
    // to the Redis blacklist — see src/application/auth/logout_use_case.py
    // and src/presentation/routers/auth_router.py) — the BFF route
    // forwards this Authorization header through to core-api and reads
    // the refresh token from the httpOnly cookie itself; this module
    // never touches the raw refresh token value at all.
    await bffRequest<undefined>("/api/bff/logout", {
      method: "POST",
      accessToken,
    });
  },

  requestPasswordReset: (email: string) =>
    request<MessageResponse>("/api/v1/auth/request-password-reset", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (payload: { token: string; new_password: string }) =>
    request<MessageResponse>("/api/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  requestEmailVerification: (email: string) =>
    request<MessageResponse>("/api/v1/auth/request-email-verification", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  verifyEmail: (token: string) =>
    request<MessageResponse>("/api/v1/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
};
