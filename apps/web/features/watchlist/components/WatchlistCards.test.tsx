import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { watchlistApi } from "../../../lib/watchlist-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { WatchlistCards } from "./WatchlistCards";

vi.mock("../../../lib/watchlist-api", () => ({
  watchlistApi: {
    listWatchlists: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("WatchlistCards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(watchlistApi.listWatchlists).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<WatchlistCards onSelectWatchlist={vi.fn()} onEditWatchlist={vi.fn()} />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there are no watchlists", async () => {
    vi.mocked(watchlistApi.listWatchlists).mockResolvedValue({
      items: [],
      total_count: 0,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<WatchlistCards onSelectWatchlist={vi.fn()} onEditWatchlist={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/don't have any watchlists yet/i)).toBeInTheDocument();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(watchlistApi.listWatchlists).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<WatchlistCards onSelectWatchlist={vi.fn()} onEditWatchlist={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders watchlist cards with the default badge and item count", async () => {
    vi.mocked(watchlistApi.listWatchlists).mockResolvedValue({
      items: [
        {
          id: "w1",
          user_id: "u1",
          name: "Tech Stocks",
          is_default: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          item_count: 3,
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 20,
    });
    renderWithQueryClient(<WatchlistCards onSelectWatchlist={vi.fn()} onEditWatchlist={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Tech Stocks")).toBeInTheDocument();
    });
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("3 symbols")).toBeInTheDocument();
  });

  it("calls onSelectWatchlist when a watchlist name is clicked", async () => {
    vi.mocked(watchlistApi.listWatchlists).mockResolvedValue({
      items: [
        {
          id: "w1",
          user_id: "u1",
          name: "Tech Stocks",
          is_default: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          item_count: 1,
        },
      ],
      total_count: 1,
      page: 1,
      page_size: 20,
    });
    const onSelectWatchlist = vi.fn();
    renderWithQueryClient(
      <WatchlistCards onSelectWatchlist={onSelectWatchlist} onEditWatchlist={vi.fn()} />
    );

    await waitFor(() => {
      expect(screen.getByText("Tech Stocks")).toBeInTheDocument();
    });
    screen.getByText("Tech Stocks").click();
    expect(onSelectWatchlist).toHaveBeenCalledWith("w1");
  });
});
