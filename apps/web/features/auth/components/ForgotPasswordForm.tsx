"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@investiq/ui";
import { type ForgotPasswordFormValues, forgotPasswordSchema } from "@investiq/validation";
import { motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError, authApi } from "../../../lib/auth-api";

export function ForgotPasswordForm() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
  });

  const onSubmit = async (values: ForgotPasswordFormValues) => {
    setServerError(null);
    setSuccessMessage(null);
    try {
      // Response is identical whether or not the account exists (Document 6
      // §15.1 enumeration mitigation) — the UI always shows the same
      // success message regardless of the backend's internal outcome.
      const result = await authApi.requestPasswordReset(values.email);
      setSuccessMessage(result.message);
    } catch (error) {
      if (error instanceof ApiError) {
        setServerError(error.message);
      } else {
        setServerError("Something went wrong. Please try again.");
      }
    }
  };

  if (successMessage) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        role="status"
        className="w-full max-w-sm rounded-md bg-accent-emerald/10 px-4 py-3 text-sm text-accent-emerald"
      >
        {successMessage}
      </motion.div>
    );
  }

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

      {serverError && (
        <p role="alert" className="rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
          {serverError}
        </p>
      )}

      <Button type="submit" disabled={isSubmitting} className="mt-2">
        {isSubmitting ? "Sending…" : "Send reset link"}
      </Button>
    </motion.form>
  );
}
