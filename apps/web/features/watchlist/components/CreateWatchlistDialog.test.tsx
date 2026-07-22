import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { watchlistApi } from "../../../lib/watchlist-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { CreateWatchlistDialog } from "./CreateWatchlistDialog";

vi.mock("../../../lib/watchlist-api", () => ({
  watchlistApi: {
    createWatchlist: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("CreateWatchlistDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    renderWithQueryClient(<CreateWatchlistDialog isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a validation error for an empty name", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateWatchlistDialog isOpen={true} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/watchlist name is required/i);
    expect(watchlistApi.createWatchlist).not.toHaveBeenCalled();
  });

  it("calls onClose and onCreated on a successful submit", async () => {
    vi.mocked(watchlistApi.createWatchlist).mockResolvedValue({
      id: "w1",
      user_id: "u1",
      name: "Tech Stocks",
      is_default: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      item_count: 0,
    });
    const onClose = vi.fn();
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(
      <CreateWatchlistDialog isOpen={true} onClose={onClose} onCreated={onCreated} />
    );

    await user.type(screen.getByLabelText(/^name$/i), "Tech Stocks");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await vi.waitFor(() => {
      expect(watchlistApi.createWatchlist).toHaveBeenCalledWith({
        name: "Tech Stocks",
        is_default: false,
      });
    });
    expect(onCreated).toHaveBeenCalledWith("w1");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a server error message when creation fails", async () => {
    vi.mocked(watchlistApi.createWatchlist).mockRejectedValue(new Error("Request failed"));
    const user = userEvent.setup();
    renderWithQueryClient(<CreateWatchlistDialog isOpen={true} onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/^name$/i), "Tech Stocks");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByText(/failed to create watchlist/i)).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<CreateWatchlistDialog isOpen={true} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
