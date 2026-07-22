"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { type UpdateWatchlistFormValues, updateWatchlistSchema } from "@investiq/validation";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../../lib/auth-api";
import { useUpdateWatchlist } from "../hooks/useWatchlists";

export interface EditWatchlistDialogProps {
  watchlistId: string;
  currentName: string;
  currentIsDefault: boolean;
  isOpen: boolean;
  onClose: () => void;
}

export function EditWatchlistDialog({
  watchlistId,
  currentName,
  currentIsDefault,
  isOpen,
  onClose,
}: EditWatchlistDialogProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const updateWatchlist = useUpdateWatchlist(watchlistId);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UpdateWatchlistFormValues>({
    resolver: zodResolver(updateWatchlistSchema),
    defaultValues: { name: currentName, isDefault: currentIsDefault },
  });

  useEffect(() => {
    reset({ name: currentName, isDefault: currentIsDefault });
  }, [currentName, currentIsDefault, reset]);

  if (!isOpen) return null;

  const onSubmit = async (values: UpdateWatchlistFormValues) => {
    setServerError(null);
    try {
      await updateWatchlist.mutateAsync({
        name: values.name,
        is_default: values.isDefault,
      });
      onClose();
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : "Failed to update watchlist.");
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-watchlist-title"
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
          <h2 id="edit-watchlist-title" className="text-lg font-semibold text-text-primary">
            Edit Watchlist
          </h2>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-4 flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="edit-name" className="text-sm font-medium text-text-primary">
                Name
              </label>
              <input
                id="edit-name"
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
                {isSubmitting ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
