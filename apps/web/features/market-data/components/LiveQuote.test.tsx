import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { marketDataApi } from "../../../lib/market-data-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { LiveQuote } from "./LiveQuote";

vi.mock("../../../lib/market-data-api", () => ({
  marketDataApi: {
    getCurrentPrice: vi.fn(),
  },
}));

describe("LiveQuote", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(marketDataApi.getCurrentPrice).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<LiveQuote symbol="AAPL" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders the quote once data loads", async () => {
    vi.mocked(marketDataApi.getCurrentPrice).mockResolvedValue({
      symbol: "AAPL",
      price: "150.00",
      previous_close: "145.00",
      source: "yfinance",
      is_stale_fallback: false,
    });

    renderWithQueryClient(<LiveQuote symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    expect(screen.getByText("$150.00")).toBeInTheDocument();
    expect(screen.getByText(/prev\. close: \$145\.00/i)).toBeInTheDocument();
  });

  it("shows an error state when the quote request fails", async () => {
    vi.mocked(marketDataApi.getCurrentPrice).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<LiveQuote symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/failed to load quote/i);
  });

  it("discloses when the quote is a stale fallback", async () => {
    vi.mocked(marketDataApi.getCurrentPrice).mockResolvedValue({
      symbol: "AAPL",
      price: "150.00",
      previous_close: null,
      source: "ohlcv_bar",
      is_stale_fallback: true,
    });

    renderWithQueryClient(<LiveQuote symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText(/\(delayed\)/i)).toBeInTheDocument();
    });
  });
});
