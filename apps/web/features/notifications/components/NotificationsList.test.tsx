import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { notificationsApi } from "../../../lib/notifications-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { NotificationsList } from "./NotificationsList";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import * as ToastModule from "../../realtime/components/Toast";
import type { RealtimeEnvelope } from "../../realtime/hooks/useRealtimeConnection";

vi.mock("../../../lib/notifications-api", () => ({
  notificationsApi: {
    listNotifications: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

type MessageListener = (envelope: RealtimeEnvelope) => void;
let capturedListener: MessageListener | undefined;

vi.mock("../../realtime/hooks/useRealtimeConnection", () => ({
  useRealtimeConnection: vi.fn(),
}));

function mockRealtimeConnection(): void {
  capturedListener = undefined;
  vi.mocked(useRealtimeConnection).mockReturnValue({
    connectionState: "connected",
    subscribe: (_topic: string, listener: MessageListener) => {
      capturedListener = listener;
      return () => {};
    },
  });
}

describe("NotificationsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRealtimeConnection();
  });

  it("shows a loading state initially", () => {
    vi.mocked(notificationsApi.listNotifications).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<NotificationsList />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    vi.mocked(notificationsApi.listNotifications).mockResolvedValue({
      items: [],
      total_count: 0,
      unread_count: 0,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByText(/don't have any notifications yet/i)).toBeInTheDocument();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(notificationsApi.listNotifications).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders notifications with unread count and a mark-all-as-read action", async () => {
    vi.mocked(notificationsApi.listNotifications).mockResolvedValue({
      items: [
        {
          id: "n1",
          user_id: "u1",
          type: "alert_triggered",
          title: "AAPL crossed $150",
          body: "Your price alert triggered.",
          metadata: {},
          is_read: false,
          read_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total_count: 1,
      unread_count: 1,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByText("AAPL crossed $150")).toBeInTheDocument();
    });
    expect(screen.getByText("1 unread notification")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mark all as read/i })).toBeInTheDocument();
  });

  it("calls markAsRead when a notification's mark as read button is clicked", async () => {
    vi.mocked(notificationsApi.listNotifications).mockResolvedValue({
      items: [
        {
          id: "n1",
          user_id: "u1",
          type: "system",
          title: "Welcome",
          body: "Welcome to INVEST IQ.",
          metadata: {},
          is_read: false,
          read_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total_count: 1,
      unread_count: 1,
      page: 1,
      page_size: 20,
    });
    vi.mocked(notificationsApi.markAsRead).mockResolvedValue({
      id: "n1",
      user_id: "u1",
      type: "system",
      title: "Welcome",
      body: "Welcome to INVEST IQ.",
      metadata: {},
      is_read: true,
      read_at: "2026-01-01T01:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    });
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByText("Welcome")).toBeInTheDocument();
    });
    screen.getByRole("button", { name: /^mark as read$/i }).click();

    await waitFor(() => {
      expect(notificationsApi.markAsRead).toHaveBeenCalledWith("n1");
    });
  });

  it("does not show a mark-as-read button for already-read notifications", async () => {
    vi.mocked(notificationsApi.listNotifications).mockResolvedValue({
      items: [
        {
          id: "n1",
          user_id: "u1",
          type: "system",
          title: "Welcome",
          body: "Welcome to INVEST IQ.",
          metadata: {},
          is_read: true,
          read_at: "2026-01-01T01:00:00Z",
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total_count: 1,
      unread_count: 0,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByText("Welcome")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /^mark as read$/i })).not.toBeInTheDocument();
  });

  it("shows an instant toast and re-fetches the list when an alert-triggered push arrives", async () => {
    const showToastSpy = vi.spyOn(ToastModule, "showToast");
    vi.mocked(notificationsApi.listNotifications).mockResolvedValue({
      items: [],
      total_count: 0,
      unread_count: 0,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<NotificationsList />);

    await waitFor(() => {
      expect(screen.getByText(/don't have any notifications yet/i)).toBeInTheDocument();
    });

    expect(capturedListener).toBeDefined();
    const callCountBeforePush = vi.mocked(notificationsApi.listNotifications).mock.calls.length;

    // Simulate AlertEvaluationStreamingService's own push (Task 8) —
    // the exact envelope shape realtime_service.py's _dispatch() builds
    // for the "alert" topic.
    capturedListener?.({
      type: "alert",
      topic: "alert",
      data: { title: "AAPL crossed $150", body: "Your price alert triggered." },
    });

    expect(showToastSpy).toHaveBeenCalledWith({
      title: "AAPL crossed $150",
      description: "Your price alert triggered.",
      variant: "warning",
    });

    await waitFor(() => {
      expect(vi.mocked(notificationsApi.listNotifications).mock.calls.length).toBeGreaterThan(
        callCountBeforePush
      );
    });
  });
});
