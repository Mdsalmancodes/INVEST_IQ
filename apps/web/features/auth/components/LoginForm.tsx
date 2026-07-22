"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@investiq/ui";
import { type LoginFormValues, loginSchema } from "@investiq/validation";
import { motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError, authApi } from "../../../lib/auth-api";

export interface LoginFormProps {
  onSuccess: (accessToken: string) => void;
}

/**
 * LoginForm — White+Purple branding (Document 2 §6.3 design tokens),
 * React Hook Form + Zod (Document 6 §15.3's shared-schema pattern),
 * loading/error/success states, accessible (Document 2 §6.5).
 */
export function LoginForm({ onSuccess }: LoginFormProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (values: LoginFormValues) => {
    setServerError(null);
    try {
      const result = await authApi.login(values);
      onSuccess(result.access_token);
    } catch (error) {
      if (error instanceof ApiError) {
        setServerError(error.message);
      } else {
        setServerError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <motion.form
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      onSubmit={handleSubmit(onSubmit)}
      className="flex w-full max-w-sm flex-col gap-4"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="email" className="text-sm font-medium text-text-primary">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-invalid={errors.email ? "true" : "false"}
          aria-describedby={errors.email ? "email-error" : undefined}
          {...register("email")}
        />
        {errors.email && (
          <p id="email-error" role="alert" className="text-sm text-danger">
            {errors.email.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="password" className="text-sm font-medium text-text-primary">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-invalid={errors.password ? "true" : "false"}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id="password-error" role="alert" className="text-sm text-danger">
            {errors.password.message}
          </p>
        )}
      </div>

      {serverError && (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {serverError}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} className="mt-2">
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </motion.form>
  );
}
