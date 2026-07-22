import { z } from "zod";

/**
 * Password constraints — MUST match the backend's domain value object
 * exactly (apps/core-api/src/domain/auth/value_objects.py:
 * MIN_PASSWORD_LENGTH=10, MAX_PASSWORD_LENGTH=128) so client-side validation
 * never accepts something the server will reject, or vice versa. The
 * common-password blocklist check (Document 6 §15.2) is server-side only —
 * duplicating a wordlist into the client bundle isn't worth the size cost,
 * and the server is the actual enforcement boundary regardless (Document 6
 * §15.3: "client-side validation is UX only, never a security boundary").
 */
export const MIN_PASSWORD_LENGTH = 10;
export const MAX_PASSWORD_LENGTH = 128;

export const emailSchema = z
  .string()
  .trim()
  .min(1, "Email is required")
  .email("Enter a valid email address");

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `Password must be at least ${MIN_PASSWORD_LENGTH} characters`)
  .max(MAX_PASSWORD_LENGTH, `Password must be at most ${MAX_PASSWORD_LENGTH} characters`);

export const fullNameSchema = z
  .string()
  .trim()
  .min(1, "Full name is required")
  .max(200, "Full name is too long");

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Password is required"),
});
export type LoginFormValues = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    fullName: fullNameSchema,
    email: emailSchema,
    password: passwordSchema,
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });
export type RegisterFormValues = z.infer<typeof registerSchema>;

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    password: passwordSchema,
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;
