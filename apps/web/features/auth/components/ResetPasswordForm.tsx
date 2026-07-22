"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@investiq/ui";
import { type ResetPasswordFormValues, resetPasswordSchema } from "@investiq/validation";
import { motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError, authApi } from "../../../lib/auth-api";
import { PasswordStrengthMeter } from "./PasswordStrengthMeter";

export interface ResetPasswordFormProps {
  token: string;
  onSuccess: () => void;
}

export function ResetPasswordForm({ token, onSuccess }: ResetPasswordFormProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
  });

  const passwordValue = watch("password") ?? "";

  const onSubmit = async (values: ResetPasswordFormValues) => {
    setServerError(null);
    try {
      await authApi.resetPassword({ token, new_password: values.password });
      onSuccess();
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
        <label htmlFor="password" className="text-sm font-medium text-text-primary">
          New password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-invalid={errors.password ? "true" : "false"}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
        <PasswordStrengthMeter password={passwordValue} />
        {errors.password && (
          <p id="password-error" role="alert" className="text-sm text-danger">
            {errors.password.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="confirmPassword" className="text-sm font-medium text-text-primary">
          Confirm new password
        </label>
        <input
          id="confirmPassword"
          type="password"
          autoComplete="new-password"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-invalid={errors.confirmPassword ? "true" : "false"}
          aria-describedby={errors.confirmPassword ? "confirmPassword-error" : undefined}
          {...register("confirmPassword")}
        />
        {errors.confirmPassword && (
          <p id="confirmPassword-error" role="alert" className="text-sm text-danger">
            {errors.confirmPassword.message}
          </p>
        )}
      </div>

      {serverError && (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {serverError}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} className="mt-2">
        {isSubmitting ? "Resetting…" : "Reset password"}
      </Button>
    </motion.form>
  );
}
