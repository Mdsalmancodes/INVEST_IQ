"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  DIGEST_FREQUENCIES,
  type UpdateNotificationPreferencesFormValues,
  updateNotificationPreferencesSchema,
} from "@investiq/validation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
} from "../hooks/useNotifications";

const DIGEST_LABELS: Record<(typeof DIGEST_FREQUENCIES)[number], string> = {
  off: "Off",
  daily: "Daily",
  weekly: "Weekly",
};

/**
 * NotificationPreferencesForm — edits the current user's notification
 * delivery preferences. Follows EditWatchlistDialog's form pattern but is
 * rendered inline (not as a modal dialog), since preferences are a
 * settings-page concept, not a per-item action.
 */
export function NotificationPreferencesForm() {
  const { data: preferences, isLoading } = useNotificationPreferences();
  const updatePreferences = useUpdateNotificationPreferences();
  const [serverError, setServerError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateNotificationPreferencesFormValues>({
    resolver: zodResolver(updateNotificationPreferencesSchema),
    defaultValues: {
      priceAlertsEmail: true,
      priceAlertsPush: true,
      digestFrequency: "daily",
      quietHoursStart: "",
      quietHoursEnd: "",
      clearQuietHours: false,
    },
  });

  useEffect(() => {
    if (preferences) {
      reset({
        priceAlertsEmail: preferences.price_alerts_email,
        priceAlertsPush: preferences.price_alerts_push,
        digestFrequency: preferences.digest_frequency,
        quietHoursStart: preferences.quiet_hours_start?.slice(0, 5) ?? "",
        quietHoursEnd: preferences.quiet_hours_end?.slice(0, 5) ?? "",
        clearQuietHours: false,
      });
    }
  }, [preferences, reset]);

  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="h-40 animate-pulse rounded-lg bg-primary-50">
        <span className="sr-only">Loading notification preferences…</span>
      </div>
    );
  }

  const onSubmit = async (values: UpdateNotificationPreferencesFormValues) => {
    setServerError(null);
    setSuccessMessage(null);
    try {
      await updatePreferences.mutateAsync({
        price_alerts_email: values.priceAlertsEmail,
        price_alerts_push: values.priceAlertsPush,
        digest_frequency: values.digestFrequency,
        quiet_hours_start: values.quietHoursStart || undefined,
        quiet_hours_end: values.quietHoursEnd || undefined,
        clear_quiet_hours: values.clearQuietHours,
      });
      setSuccessMessage("Preferences saved.");
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Failed to save preferences."
      );
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      <label className="flex items-center gap-2 text-sm text-text-primary">
        <input type="checkbox" {...register("priceAlertsEmail")} />
        Email me when a price alert triggers
      </label>

      <label className="flex items-center gap-2 text-sm text-text-primary">
        <input type="checkbox" {...register("priceAlertsPush")} />
        Push notify me when a price alert triggers
      </label>

      <div className="flex flex-col gap-1">
        <label htmlFor="digest-frequency" className="text-sm font-medium text-text-primary">
          Digest frequency
        </label>
        <select
          id="digest-frequency"
          className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
          {...register("digestFrequency")}
        >
          {DIGEST_FREQUENCIES.map((frequency) => (
            <option key={frequency} value={frequency}>
              {DIGEST_LABELS[frequency]}
            </option>
          ))}
        </select>
      </div>

      <div className="flex gap-3">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="quiet-hours-start" className="text-sm font-medium text-text-primary">
            Quiet hours start
          </label>
          <input
            id="quiet-hours-start"
            type="time"
            className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
            aria-invalid={errors.quietHoursStart ? "true" : "false"}
            {...register("quietHoursStart")}
          />
        </div>
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="quiet-hours-end" className="text-sm font-medium text-text-primary">
            Quiet hours end
          </label>
          <input
            id="quiet-hours-end"
            type="time"
            className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
            aria-invalid={errors.quietHoursEnd ? "true" : "false"}
            {...register("quietHoursEnd")}
          />
        </div>
      </div>
      {(errors.quietHoursStart || errors.quietHoursEnd) && (
        <p role="alert" className="text-sm text-danger">
          {errors.quietHoursEnd?.message ?? errors.quietHoursStart?.message}
        </p>
      )}

      {serverError && (
        <p role="alert" className="text-sm text-danger">
          {serverError}
        </p>
      )}
      {successMessage && (
        <p role="status" className="text-sm text-success">
          {successMessage}
        </p>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        className="self-end rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {isSubmitting ? "Saving…" : "Save Preferences"}
      </button>
    </form>
  );
}
