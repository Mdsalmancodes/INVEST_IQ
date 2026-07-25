"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  CONDITION_TYPES,
  type CreateAlertFormValues,
  createAlertSchema,
} from "@investiq/validation";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import { useCreateAlert } from "../hooks/useAlerts";

export interface CreateAlertDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (alertId: string) => void;
}

const CONDITION_LABELS: Record<(typeof CONDITION_TYPES)[number], string> = {
  price_above: "Price rises above",
  price_below: "Price falls below",
  pct_change: "Percent change exceeds",
  rsi_threshold: "RSI crosses",
};

export function CreateAlertDialog({ isOpen, onClose, onCreated }: CreateAlertDialogProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const createAlert = useCreateAlert();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateAlertFormValues>({
    resolver: zodResolver(createAlertSchema),
    defaultValues: {
      symbol: "",
      conditionType: "price_above",
      threshold: "",
      isRecurring: false,
      cooldownMinutes: 0,
    },
  });

  if (!isOpen) return null;

  const onSubmit = async (values: CreateAlertFormValues) => {
    setServerError(null);
    try {
      const created = await createAlert.mutateAsync({
        symbol: values.symbol,
        condition_type: values.conditionType,
        threshold: values.threshold,
        is_recurring: values.isRecurring,
        cooldown_minutes: values.cooldownMinutes,
      });
      reset();
      onCreated?.(created.id);
      onClose();
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Failed to create alert.");
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-alert-title"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md rounded-lg bg-surface p-6 shadow-lg"
        >
          <h2 id="create-alert-title" className="text-lg font-semibold text-text-primary">
            Create Alert
          </h2>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-4 flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="alert-symbol" className="text-sm font-medium text-text-primary">
                Symbol
              </label>
              <input
                id="alert-symbol"
                type="text"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.symbol ? "true" : "false"}
                {...register("symbol")}
              />
              {errors.symbol && (
                <p role="alert" className="text-sm text-danger">
                  {errors.symbol.message}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="alert-condition" className="text-sm font-medium text-text-primary">
                Condition
              </label>
              <select
                id="alert-condition"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                {...register("conditionType")}
              >
                {CONDITION_TYPES.map((conditionType) => (
                  <option key={conditionType} value={conditionType}>
                    {CONDITION_LABELS[conditionType]}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="alert-threshold" className="text-sm font-medium text-text-primary">
                Threshold
              </label>
              <input
                id="alert-threshold"
                type="text"
                inputMode="decimal"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.threshold ? "true" : "false"}
                {...register("threshold")}
              />
              {errors.threshold && (
                <p role="alert" className="text-sm text-danger">
                  {errors.threshold.message}
                </p>
              )}
            </div>

            <label className="flex items-center gap-2 text-sm text-text-primary">
              <input type="checkbox" {...register("isRecurring")} />
              Repeat this alert (with a cooldown)
            </label>

            <div className="flex flex-col gap-1">
              <label htmlFor="alert-cooldown" className="text-sm font-medium text-text-primary">
                Cooldown (minutes)
              </label>
              <input
                id="alert-cooldown"
                type="number"
                min={0}
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.cooldownMinutes ? "true" : "false"}
                {...register("cooldownMinutes", { valueAsNumber: true })}
              />
              {errors.cooldownMinutes && (
                <p role="alert" className="text-sm text-danger">
                  {errors.cooldownMinutes.message}
                </p>
              )}
            </div>

            {serverError && (
              <p role="alert" className="text-sm text-danger">
                {serverError}
              </p>
            )}

            <div className="mt-2 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {isSubmitting ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
