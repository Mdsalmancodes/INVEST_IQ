"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@investiq/ui";
import { type RegisterFormValues, registerSchema } from "@investiq/validation";
import { motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError, authApi } from "../../../lib/auth-api";
import { PasswordStrengthMeter } from "./PasswordStrengthMeter";

export interface RegisterFormProps {
  onSuccess: (email: string) => void;
}

export function RegisterForm({ onSuccess }: RegisterFormProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
  });

  const passwordValue = watch("password") ?? "";

  const onSubmit = async (values: RegisterFormValues) => {
    setServerError(null);
    try {
      await authApi.register({
        email: values.email,
        password: values.password,
        full_name: values.fullName,
      });
      onSuccess(values.email);
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
        <label htmlFor="fullName" className="text-sm font-medium text-text-primary">
          Full name
        </label>
        <input
          id="fullName"
          type="text"
          autoComplete="name"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-invalid={errors.fullName ? "true" : "false"}
          aria-describedby={errors.fullName ? "fullName-error" : undefined}
          {...register("fullName")}
        />
        {errors.fullName && (
          <p id="fullName-error" role="alert" className="text-sm text-danger">
            {errors.fullName.message}
          </p>
        )}
      </div>

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
          Confirm password
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
        {isSubmitting ? "Creating account…" : "Create account"}
      </Button>
    </motion.form>
  );
}
