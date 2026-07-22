import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { portfolioApi } from "../../../lib/portfolio-api";
import { renderWithQueryClient } from "../test-utils";
import { PortfolioSummaryCards } from "./PortfolioSummaryCards";

vi.mock("../../../lib/portfolio-api", () => ({
  portfolioApi: {
    getSummary: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("PortfolioSummaryCards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(portfolioApi.getSummary).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<PortfolioSummaryCards portfolioId="p1" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders the summary cards once data loads", async () => {
    vi.mocked(portfolioApi.getSummary).mockResolvedValue({
      portfolio_id: "p1",
      total_investment: "1000.00000000",
      current_value: "1200.00000000",
      profit_loss: "200.00000000",
      profit_loss_pct: "20",
      realized_gain: "0.00000000",
      unrealized_gain: "200.00000000",
      dividend_income: "0.00000000",
      daily_gain: "10.00000000",
      holdings: [],
      holdings_missing_price: [],
    });

    renderWithQueryClient(<PortfolioSummaryCards portfolioId="p1" />);

    await waitFor(() => {
      expect(screen.getByText("Total Investment")).toBeInTheDocument();
    });
    expect(screen.getByText("$1,000.00")).toBeInTheDocument();
    expect(screen.getByText("$1,200.00")).toBeInTheDocument();
    expect(screen.getByText("+20.00%")).toBeInTheDocument();
  });

  it("shows an error state when the summary request fails", async () => {
    vi.mocked(portfolioApi.getSummary).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<PortfolioSummaryCards portfolioId="p1" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/failed to load portfolio summary/i);
  });

  it("shows a missing-price disclosure banner when holdings are missing prices", async () => {
    vi.mocked(portfolioApi.getSummary).mockResolvedValue({
      portfolio_id: "p1",
      total_investment: "1000.00000000",
      current_value: "0.00000000",
      profit_loss: "-1000.00000000",
      profit_loss_pct: "-100",
      realized_gain: "0.00000000",
      unrealized_gain: "0.00000000",
      dividend_income: "0.00000000",
      daily_gain: "0.00000000",
      holdings: [
        {
          instrument_id: "instrument-1",
          quantity: "10",
          average_buy_price: "100.00000000",
          current_price: null,
          market_value: null,
          unrealized_gain: null,
          allocation_pct: null,
          daily_gain: null,
        },
      ],
      holdings_missing_price: ["instrument-1"],
    });

    renderWithQueryClient(<PortfolioSummaryCards portfolioId="p1" />);

    await waitFor(() => {
      expect(screen.getByText(/missing current price data/i)).toBeInTheDocument();
    });
  });
});
