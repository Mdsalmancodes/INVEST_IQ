import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { showToast, ToastContainer, useToastStore } from "./Toast";

/**
 * Toast tests — the toast queue (useToastStore) and its convenience
 * showToast() function, plus ToastContainer's rendering of the queue.
 * Previously only exercised indirectly through NotificationsList's own
 * "shows a toast on an alert push" wiring (Task 12) — this file tests
 * the primitive's own contract directly.
 */
describe("Toast", () => {
  beforeEach(() => {
    // Clear any toasts left over from a previous test — the store is a
    // module-level singleton (Zustand), so state persists across tests
    // in the same file unless reset.
    useToastStore.setState({ toasts: [] });
  });

  it("showToast is callable from outside any component and adds a toast to the store", () => {
    showToast({ title: "Alert triggered", description: "AAPL crossed $150", variant: "warning" });

    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      title: "Alert triggered",
      description: "AAPL crossed $150",
      variant: "warning",
    });
  });

  it("ToastContainer renders every currently-queued toast's title and description", () => {
    act(() => {
      showToast({ title: "First toast", description: "First body", variant: "info" });
      showToast({ title: "Second toast", description: "Second body", variant: "success" });
    });

    render(<ToastContainer />);

    expect(screen.getByText("First toast")).toBeInTheDocument();
    expect(screen.getByText("First body")).toBeInTheDocument();
    expect(screen.getByText("Second toast")).toBeInTheDocument();
  });

  it("dismisses a toast when its close button is clicked", async () => {
    act(() => {
      showToast({ title: "Dismiss me", variant: "danger" });
    });
    render(<ToastContainer />);
    expect(screen.getByText("Dismiss me")).toBeInTheDocument();

    act(() => {
      screen.getByRole("button", { name: /dismiss notification/i }).click();
    });

    await waitFor(() => {
      expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument();
    });
  });

  it("auto-dismisses a toast after the default timeout", () => {
    vi.useFakeTimers();
    act(() => {
      showToast({ title: "Auto dismiss", variant: "info" });
    });
    expect(useToastStore.getState().toasts).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(6_000);
    });

    expect(useToastStore.getState().toasts).toHaveLength(0);
    vi.useRealTimers();
  });

  it("renders nothing extra when the toast queue is empty", () => {
    render(<ToastContainer />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
