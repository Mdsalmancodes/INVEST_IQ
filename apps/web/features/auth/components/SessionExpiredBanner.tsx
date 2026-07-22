"use client";

import { Button } from "@investiq/ui";
import { AnimatePresence, motion } from "motion/react";

export interface SessionExpiredBannerProps {
  isVisible: boolean;
  onReLogin: () => void;
  onDismiss: () => void;
}

/**
 * Shown when the current access token has expired AND the refresh attempt
 * also failed (Document 3 §7.4) — e.g. the refresh token itself expired,
 * was revoked, or reuse was detected. Distinct from a silent-refresh retry,
 * which happens transparently without ever showing this banner.
 */
export function SessionExpiredBanner({
  isVisible,
  onReLogin,
  onDismiss,
}: SessionExpiredBannerProps) {
  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.25 }}
          role="alert"
          className="fixed inset-x-0 top-0 z-50 flex items-center justify-between gap-4 bg-dark px-4 py-3 text-white shadow-lg"
        >
          <p className="text-sm">
            Your session has expired. Please sign in again to continue.
          </p>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="primary" onClick={onReLogin}>
              Sign in
            </Button>
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss"
              className="rounded-md p-1 text-white/70 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              ×
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
