import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { watchlistApi } from "../../../lib/watchlist-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { EditWatchlistDialog } from "./EditWatchlistDialog";

vi.mock("../../../lib/watchlist-api", () => ({
  watchlistApi: {
    updateWatchlist: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("EditWatchlistDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    renderWithQueryClient(
      <EditWatchlistDialog
        watchlistId="w1"
        currentName="Tech Stocks"
        currentIsDefault={false}
        isOpen={false}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("pre-fills the form with the current name and default flag", () => {
    renderWithQueryClient(
      <EditWatchlistDialog
        watchlistId="w1"
        currentName="Tech Stocks"
        currentIsDefault={true}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByLabelText(/^name$/i)).toHaveValue("Tech Stocks");
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("submits the updated name", async () => {
    vi.mocked(watchlistApi.updateWatchlist).mockResolvedValue({
      id: "w1",
      user_id: "u1",
      name: "Renamed",
      is_default: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      item_count: 0,
    });
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(
      <EditWatchlistDialog
        watchlistId="w1"
        currentName="Tech Stocks"
        currentIsDefault={false}
        isOpen={true}
        onClose={onClose}
      />
    );

    await user.clear(screen.getByLabelText(/^name$/i));
    await user.type(screen.getByLabelText(/^name$/i), "Renamed");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() => {
      expect(watchlistApi.updateWatchlist).toHaveBeenCalledWith("w1", {
        name: "Renamed",
        is_default: false,
      });
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a server error message when the update fails", async () => {
    vi.mocked(watchlistApi.updateWatchlist).mockRejectedValue(new Error("Request failed"));
    const user = userEvent.setup();
    renderWithQueryClient(
      <EditWatchlistDialog
        watchlistId="w1"
        currentName="Tech Stocks"
        currentIsDefault={false}
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/failed to update watchlist/i)).toBeInTheDocument();
  });
});
