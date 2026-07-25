import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { watchlistApi } from "../../../lib/watchlist-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { WatchlistTable } from "./WatchlistTable";

vi.mock("../../../lib/watchlist-api", () => ({
  watchlistApi: {
    getWatchlist: vi.fn(),
    updateItem: vi.fn(),
    removeItem: vi.fn(),
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

const BASE_WATCHLIST = {
  id: "w1",
  user_id: "u1",
  name: "Tech Stocks",
  is_default: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  market_status: "open",
};

describe("WatchlistTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(watchlistApi.getWatchlist).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state when the watchlist has no items", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockResolvedValue({ ...BASE_WATCHLIST, items: [] });
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByText(/this watchlist is empty/i)).toBeInTheDocument();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders item quotes with price/daily change/market status", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockResolvedValue({
      ...BASE_WATCHLIST,
      items: [
        {
          id: "item-1",
          instrument_id: "inst-1",
          symbol: "AAPL",
          position: 0,
          is_pinned: false,
          added_at: "2026-01-01T00:00:00Z",
          quote: {
            price: "150.00",
            previous_close: "145.00",
            daily_change: "5.00",
            daily_change_pct: "3.45",
            source: "yfinance",
            is_delayed: false,
            last_updated: null,
            error: null,
          },
        },
      ],
    });
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
  });

  it("shows a per-item error when the quote failed", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockResolvedValue({
      ...BASE_WATCHLIST,
      items: [
        {
          id: "item-1",
          instrument_id: "inst-1",
          symbol: "AAPL",
          position: 0,
          is_pinned: false,
          added_at: "2026-01-01T00:00:00Z",
          quote: {
            price: null,
            previous_close: null,
            daily_change: null,
            daily_change_pct: null,
            source: null,
            is_delayed: false,
            last_updated: null,
            error: "provider network error",
          },
        },
      ],
    });
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByText("provider network error")).toBeInTheDocument();
    });
  });

  it("toggles pin state when the pin button is clicked", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockResolvedValue({
      ...BASE_WATCHLIST,
      items: [
        {
          id: "item-1",
          instrument_id: "inst-1",
          symbol: "AAPL",
          position: 0,
          is_pinned: false,
          added_at: "2026-01-01T00:00:00Z",
          quote: null,
        },
      ],
    });
    vi.mocked(watchlistApi.updateItem).mockResolvedValue({
      id: "item-1",
      instrument_id: "inst-1",
      symbol: "AAPL",
      position: 0,
      is_pinned: true,
      added_at: "2026-01-01T00:00:00Z",
      quote: null,
    });
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByText("☆")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("☆"));

    await waitFor(() => {
      expect(watchlistApi.updateItem).toHaveBeenCalledWith("w1", "item-1", { is_pinned: true });
    });
  });

  it("removes an item when Remove is clicked", async () => {
    vi.mocked(watchlistApi.getWatchlist).mockResolvedValue({
      ...BASE_WATCHLIST,
      items: [
        {
          id: "item-1",
          instrument_id: "inst-1",
          symbol: "AAPL",
          position: 0,
          is_pinned: false,
          added_at: "2026-01-01T00:00:00Z",
          quote: null,
        },
      ],
    });
    vi.mocked(watchlistApi.removeItem).mockResolvedValue(undefined);
    renderWithQueryClient(<WatchlistTable watchlistId="w1" />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /remove/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));

    await waitFor(() => {
      expect(watchlistApi.removeItem).toHaveBeenCalledWith("w1", "item-1");
    });
  });
});
