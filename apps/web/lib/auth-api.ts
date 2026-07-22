/**
 * Typed API client for auth endpoints — Document 2 §5.2's "typed fetch
 * wrapper, interceptors, error mapping" (lib/api-client.ts pattern),
 * scoped to auth for Phase 2. Talks to the BFF route handlers (not
 * core-api directly from the browser) — Document 3 §7.3.
 *
 * REFRESH TOKEN HANDLING (Phase 2 interim, disclosed in the Phase 2
 * verification report's known-issues section): Document 3 §7.4's real
 * design has the BFF intercept /login and /refresh responses, strip the
 * refresh token out, and set it as an httpOnly/secure/sameSite=strict
 * cookie — invisible to JS entirely. That BFF interception layer is not
 * yet built in Phase 2 (auth_router.py currently returns both tokens
 * directly in the JSON body). As an interim that is still strictly better
 * than the anti-pattern this architecture explicitly warns against
 * (localStorage, Document 3 §7.4), this module holds the refresh token in
 * a private, non-exported module-level variable — never in Zustand/React
 * state (which would make it inspectable via React/Redux devtools) and
 * never in localStorage (persists across tabs/sessions, worse XSS blast
 * radius). This is still readable by any script executing on the page
 * (true of any in-memory JS value), so it is NOT equivalent to the
 * httpOnly-cookie protection the frozen architecture specifies — it is a
 * disclosed, narrower interim, not a substitute.
 */

let refreshTokenInMemory: string | null = null;

export function setRefreshToken(token: string | null): void {
  refreshTokenInMemory = token;
}

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

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
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

  login: async (payload: { email: string; password: string }) => {
    const result = await request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setRefreshToken(result.refresh_token);
    return result;
  },

  refreshAccessToken: async () => {
    if (refreshTokenInMemory === null) {
      throw new ApiError("NO_REFRESH_TOKEN", "No active session to refresh", 401);
    }
    const result = await request<LoginResponse>("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshTokenInMemory }),
    });
    setRefreshToken(result.refresh_token); // rotation — Document 3 §7.4
    return result;
  },

  logoutCurrentSession: async () => {
    if (refreshTokenInMemory === null) return;
    await request<undefined>("/api/v1/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshTokenInMemory }),
    });
    setRefreshToken(null);
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
