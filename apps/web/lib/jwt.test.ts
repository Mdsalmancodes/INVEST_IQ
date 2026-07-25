import { describe, expect, it } from "vitest";

import { decodeAccessToken } from "./jwt";

function base64UrlEncode(input: string): string {
  return btoa(input).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function makeToken(payload: Record<string, unknown>): string {
  const header = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT", kid: "test" }));
  const body = base64UrlEncode(JSON.stringify(payload));
  // Signature is irrelevant — decodeAccessToken never verifies it, matching
  // the module's own documented scope (UI-rendering claims only).
  return `${header}.${body}.fake-signature`;
}

describe("decodeAccessToken", () => {
  it("decodes a well-formed token's userId, role, and expiresAt", () => {
    const exp = Math.floor(Date.now() / 1000) + 900;
    const token = makeToken({ sub: "user-123", role: "admin", exp });

    const decoded = decodeAccessToken(token);

    expect(decoded).toEqual({ userId: "user-123", role: "admin", expiresAt: exp * 1000 });
  });

  it("accepts every valid backend role", () => {
    for (const role of ["user", "pro_user", "admin", "super_admin"]) {
      const token = makeToken({ sub: "u", role });
      expect(decodeAccessToken(token)?.role).toBe(role);
    }
  });

  it("returns null for a token with an unrecognized role", () => {
    const token = makeToken({ sub: "u", role: "not_a_real_role" });
    expect(decodeAccessToken(token)).toBeNull();
  });

  it("returns null for a malformed token (wrong number of segments)", () => {
    expect(decodeAccessToken("not-a-jwt")).toBeNull();
  });

  it("returns null for a token missing the role claim", () => {
    const token = makeToken({ sub: "u" });
    expect(decodeAccessToken(token)).toBeNull();
  });

  it("returns null for unparsable base64/JSON in the payload segment", () => {
    expect(decodeAccessToken("header.%%%notbase64%%%.sig")).toBeNull();
  });

  it("returns expiresAt null when the exp claim is absent", () => {
    const token = makeToken({ sub: "u", role: "user" });
    expect(decodeAccessToken(token)?.expiresAt).toBeNull();
  });
});
