import { describe, expect, it } from "vitest";

import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  forgotPasswordSchema,
  loginSchema,
  registerSchema,
  resetPasswordSchema,
} from "./auth";

describe("loginSchema", () => {
  it("accepts a valid login payload", () => {
    const result = loginSchema.safeParse({ email: "user@example.com", password: "anything" });
    expect(result.success).toBe(true);
  });

  it("rejects an invalid email format", () => {
    const result = loginSchema.safeParse({ email: "not-an-email", password: "anything" });
    expect(result.success).toBe(false);
  });

  it("rejects an empty password", () => {
    const result = loginSchema.safeParse({ email: "user@example.com", password: "" });
    expect(result.success).toBe(false);
  });
});

describe("registerSchema", () => {
  const validPassword = "a-genuinely-strong-passphrase";

  it("accepts a valid registration payload", () => {
    const result = registerSchema.safeParse({
      fullName: "Jane Investor",
      email: "jane@example.com",
      password: validPassword,
      confirmPassword: validPassword,
    });
    expect(result.success).toBe(true);
  });

  it("rejects mismatched passwords", () => {
    const result = registerSchema.safeParse({
      fullName: "Jane Investor",
      email: "jane@example.com",
      password: validPassword,
      confirmPassword: "a-different-passphrase",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(["confirmPassword"]);
    }
  });

  it(`rejects a password shorter than ${MIN_PASSWORD_LENGTH} characters`, () => {
    const shortPassword = "a".repeat(MIN_PASSWORD_LENGTH - 1);
    const result = registerSchema.safeParse({
      fullName: "Jane Investor",
      email: "jane@example.com",
      password: shortPassword,
      confirmPassword: shortPassword,
    });
    expect(result.success).toBe(false);
  });

  it(`rejects a password longer than ${MAX_PASSWORD_LENGTH} characters`, () => {
    const longPassword = "a".repeat(MAX_PASSWORD_LENGTH + 1);
    const result = registerSchema.safeParse({
      fullName: "Jane Investor",
      email: "jane@example.com",
      password: longPassword,
      confirmPassword: longPassword,
    });
    expect(result.success).toBe(false);
  });

  it("rejects an empty full name", () => {
    const result = registerSchema.safeParse({
      fullName: "",
      email: "jane@example.com",
      password: validPassword,
      confirmPassword: validPassword,
    });
    expect(result.success).toBe(false);
  });

  it("trims whitespace from the full name", () => {
    const result = registerSchema.safeParse({
      fullName: "  Jane Investor  ",
      email: "jane@example.com",
      password: validPassword,
      confirmPassword: validPassword,
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fullName).toBe("Jane Investor");
    }
  });
});

describe("forgotPasswordSchema", () => {
  it("accepts a valid email", () => {
    expect(forgotPasswordSchema.safeParse({ email: "user@example.com" }).success).toBe(true);
  });

  it("rejects an invalid email", () => {
    expect(forgotPasswordSchema.safeParse({ email: "invalid" }).success).toBe(false);
  });
});

describe("resetPasswordSchema", () => {
  it("accepts matching passwords", () => {
    const password = "a-genuinely-strong-passphrase";
    const result = resetPasswordSchema.safeParse({
      password,
      confirmPassword: password,
    });
    expect(result.success).toBe(true);
  });

  it("rejects mismatched passwords", () => {
    const result = resetPasswordSchema.safeParse({
      password: "a-genuinely-strong-passphrase",
      confirmPassword: "a-totally-different-passphrase",
    });
    expect(result.success).toBe(false);
  });
});
