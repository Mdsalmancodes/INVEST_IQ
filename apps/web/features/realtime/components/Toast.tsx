"use client";

import { AnimatePresence, motion } from "motion/react";
import { create } from "zustand";

/**
 * Minimal in-house toast notification system — Phase 9's "toast
 * notifications" requirement. No toast library exists anywhere in this
 * monorepo (confirmed in Task 1's investigation) — built in-house here
 * rather than adding a new dependency, matching this codebase's
 * consistent pattern of small purpose-built code over pulling in a
 * library for a narrow need (lib/jwt.ts's own JWT decoder is the
 * precedent for this reasoning). Placed in apps/web (not packages/ui)
 * for the same `motion`-dependency reason as AnimatedNumber.tsx.
 *
 * Uses Zustand (already a dependency, and already this codebase's
 * choice for cross-cutting client state per store/auth-store.ts) for the
 * toast queue — a plain module-level array + listeners would reinvent
 * exactly what Zustand already provides.
 *
 * Any code anywhere (a component, a hook, an event handler) can call
 * `showToast(...)` directly — it does not need to be inside a React
 * component tree, since it's a plain store action, not a context. This
 * matters for Task 12: an alert-triggered WebSocket message arriving via
 * useRealtimeConnection's subscribe() callback (not itself a component)
 * needs to be able to raise a toast instantly.
 */

export type ToastVariant = "info" | "success" | "warning" | "danger";

export interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastState {
  toasts: ToastMessage[];
  show: (toast: Omit<ToastMessage, "id">) => void;
  dismiss: (id: string) => void;
}

const DEFAULT_AUTO_DISMISS_MS = 6_000;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  show: (toast) => {
    const id = crypto.randomUUID();
    set({ toasts: [...get().toasts, { ...toast, id }] });
    setTimeout(() => get().dismiss(id), DEFAULT_AUTO_DISMISS_MS);
  },
  dismiss: (id) => {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },
}));

/** Convenience function for non-component callers (e.g. a
 * useRealtimeConnection subscribe() listener) — equivalent to calling
 * useToastStore.getState().show(...) directly, just a shorter public API. */
export function showToast(toast: Omit<ToastMessage, "id">): void {
  useToastStore.getState().show(toast);
}

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  info: "glass text-text-primary",
  success: "border-success/40 bg-success/5 text-success",
  warning: "border-warning/40 bg-warning/5 text-text-primary",
  danger: "border-danger/40 bg-danger/5 text-danger",
};

/**
 * ToastContainer — mount ONCE near the root of the authenticated app
 * (e.g. a dashboard layout), matching useSessionManager's own "mount
 * once near the root" convention. Renders every currently-queued toast,
 * each dismissible early via a close button, animated in/out with
 * `motion` (already a dependency).
 */
export function ToastContainer() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2"
      aria-live="polite"
    >
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            role="status"
            initial={{ opacity: 0, y: 12, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.2 }}
            className={`pointer-events-auto rounded-lg border p-4 shadow-md ${VARIANT_CLASSES[toast.variant]}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold">{toast.title}</p>
                {toast.description && (
                  <p className="mt-1 text-sm opacity-90">{toast.description}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="text-sm opacity-60 hover:opacity-100"
              >
                ×
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
