import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { watchlistApi } from "../../../lib/watchlist-api";
import { ApiError } from "../../../lib/auth-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { AddSymbolDialog } from "./AddSymbolDialog";

vi.mock("../../../lib/watchlist-api", () => ({
  watchlistApi: {
    addItem: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

vi.mock("../../market-data/components/StockSearch", () => ({
  StockSearch: ({ onSelect }: { onSelect: (symbol: string) => void }) => (
    <button type="button" onClick={() => onSelect("AAPL")}>
      Mock StockSearch
    </button>
  ),
}));

describe("AddSymbolDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    renderWithQueryClient(<AddSymbolDialog watchlistId="w1" isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("calls addItem when a symbol is selected", async () => {
    vi.mocked(watchlistApi.addItem).mockResolvedValue({
      id: "item-1",
      instrument_id: "inst-1",
      symbol: "AAPL",
      position: 0,
      is_pinned: false,
      added_at: "2026-01-01T00:00:00Z",
      quote: null,
    });
    renderWithQueryClient(<AddSymbolDialog watchlistId="w1" isOpen={true} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Mock StockSearch"));

    await waitFor(() => {
      expect(watchlistApi.addItem).toHaveBeenCalledWith("w1", { symbol: "AAPL" });
    });
  });

  it("surfaces a duplicate-symbol error message", async () => {
    vi.mocked(watchlistApi.addItem).mockRejectedValue(
      new ApiError("CONFLICT", "Instrument AAPL is already in this watchlist", 409)
    );
    renderWithQueryClient(<AddSymbolDialog watchlistId="w1" isOpen={true} onClose={vi.fn()} />);

    fireEvent.click(screen.getByText("Mock StockSearch"));

    expect(
      await screen.findByText(/already in this watchlist/i)
    ).toBeInTheDocument();
  });
});
