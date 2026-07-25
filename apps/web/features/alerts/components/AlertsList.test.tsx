import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { alertsApi } from "../../../lib/alerts-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { AlertsList } from "./AlertsList";

vi.mock("../../../lib/alerts-api", () => ({
  alertsApi: {
    listAlerts: vi.fn(),
    updateAlert: vi.fn(),
    deleteAlert: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

vi.mock("../../realtime/hooks/useRealtimeConnection", () => ({
  useRealtimeConnection: () => ({
    connectionState: "connected",
    subscribe: () => () => {},
  }),
}));

describe("AlertsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(alertsApi.listAlerts).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<AlertsList />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state when there are no alerts", async () => {
    vi.mocked(alertsApi.listAlerts).mockResolvedValue({
      items: [],
      total_count: 0,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<AlertsList />);

    await waitFor(() => {
      expect(screen.getByText(/don't have any alerts yet/i)).toBeInTheDocument();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(alertsApi.listAlerts).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<AlertsList />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders alert rows with symbol, condition, threshold, and status", async () => {
    vi.mocked(alertsApi.listAlerts).mockResolvedValue({
      items: [
        {
          id: "a1",
          user_id: "u1",
          instrument_id: "i1",
          symbol: "AAPL",
          condition_type: "price_above",
          threshold: "150",
          is_recurring: false,
          cooldown_minutes: 0,
          is_active: true,
          triggered_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<AlertsList />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    expect(screen.getByText("Price above")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("calls deleteAlert when Delete is clicked", async () => {
    vi.mocked(alertsApi.listAlerts).mockResolvedValue({
      items: [
        {
          id: "a1",
          user_id: "u1",
          instrument_id: "i1",
          symbol: "AAPL",
          condition_type: "price_above",
          threshold: "150",
          is_recurring: false,
          cooldown_minutes: 0,
          is_active: true,
          triggered_at: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 20,
    });
    vi.mocked(alertsApi.deleteAlert).mockResolvedValue(undefined);
    renderWithQueryClient(<AlertsList />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    screen.getByRole("button", { name: /delete/i }).click();

    await waitFor(() => {
      expect(alertsApi.deleteAlert).toHaveBeenCalledWith("a1");
    });
  });
});
