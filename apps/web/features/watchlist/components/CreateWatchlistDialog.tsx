"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { type CreateWatchlistFormValues, createWatchlistSchema } from "@investiq/validation";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import { useCreateWatchlist } from "../hooks/useWatchlists";

export interface CreateWatchlistDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (watchlistId: string) => void;
}

export function CreateWatchlistDialog({
  isOpen,
  onClose,
  onCreated,
}: CreateWatchlistDialogProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const createWatchlist = useCreateWatchlist();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateWatchlistFormValues>({
    resolver: zodResolver(createWatchlistSchema),
    defaultValues: { name: "", isDefault: false },
  });

  if (!isOpen) return null;

  const onSubmit = async (values: CreateWatchlistFormValues) => {
    setServerError(null);
    try {
      const created = await createWatchlist.mutateAsync({
        name: values.name,
        is_default: values.isDefault,
      });
      reset();
      onCreated?.(created.id);
      onClose();
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Failed to create watchlist.");
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-watchlist-title"
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
          <h2 id="create-watchlist-title" className="text-lg font-semibold text-text-primary">
            Create Watchlist
          </h2>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-4 flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="name" className="text-sm font-medium text-text-primary">
                Name
              </label>
              <input
                id="name"
                type="text"
                className="h-11 rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
                aria-invalid={errors.name ? "true" : "false"}
                {...register("name")}
              />
              {errors.name && (
                <p role="alert" className="text-sm text-danger">
                  {errors.name.message}
                </p>
              )}
            </div>

            <label className="flex items-center gap-2 text-sm text-text-primary">
              <input type="checkbox" {...register("isDefault")} />
              Set as default watchlist
            </label>

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
