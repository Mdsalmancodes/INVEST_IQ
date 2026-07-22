import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { marketDataApi } from "../../../lib/market-data-api";
import { StockSearch } from "./StockSearch";

vi.mock("../../../lib/market-data-api", () => ({
  marketDataApi: {
    searchInstruments: vi.fn(),
  },
}));

function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("StockSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not search until the user types something", () => {
    renderWithQueryClient(<StockSearch onSelect={vi.fn()} />);
    expect(marketDataApi.searchInstruments).not.toHaveBeenCalled();
  });

  it("debounces input and calls the search API, then invokes onSelect", async () => {
    vi.mocked(marketDataApi.searchInstruments).mockResolvedValue({
      items: [
        {
          id: "instrument-1",
          symbol: "AAPL",
          exchange: "NASDAQ",
          name: "Apple Inc.",
          asset_type: "equity",
          currency: "USD",
        },
      ],
    });
    const onSelect = vi.fn();

    renderWithQueryClient(<StockSearch onSelect={onSelect} />);
    fireEvent.change(screen.getByLabelText(/search for a stock/i), {
      target: { value: "AAPL" },
    });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(marketDataApi.searchInstruments).toHaveBeenCalledWith("AAPL");
    });

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /aapl/i }));
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });

  it("shows a no-results message when the search returns nothing", async () => {
    vi.mocked(marketDataApi.searchInstruments).mockResolvedValue({ items: [] });

    renderWithQueryClient(<StockSearch onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/search for a stock/i), {
      target: { value: "ZZZZ" },
    });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByText(/no matching instruments found/i)).toBeInTheDocument();
    });
  });
});
