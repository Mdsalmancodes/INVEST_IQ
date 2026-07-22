import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { marketDataApi } from "../../../lib/market-data-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { InstrumentDetails } from "./InstrumentDetails";

vi.mock("../../../lib/market-data-api", () => ({
  marketDataApi: {
    getCurrentPrice: vi.fn(),
    getHistoricalPrices: vi.fn(),
    getOhlcvBars: vi.fn(),
    getCorporateActions: vi.fn(),
  },
}));

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({ setData: vi.fn() })),
    remove: vi.fn(),
    applyOptions: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
  })),
  CandlestickSeries: "CandlestickSeries",
  LineSeries: "LineSeries",
  ColorType: { Solid: "solid" },
}));

vi.mock("motion/react", () => ({
  motion: { div: "div" },
}));

describe("InstrumentDetails", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(marketDataApi.getCurrentPrice).mockResolvedValue({
      symbol: "AAPL",
      price: "150.00",
      previous_close: "145.00",
      source: "yfinance",
      is_stale_fallback: false,
    });
    vi.mocked(marketDataApi.getHistoricalPrices).mockResolvedValue({
      symbol: "AAPL",
      interval: "1d",
      data_completeness: "complete",
      points: [{ as_of: "2024-01-01T00:00:00Z", price: "150.00" }],
    });
    vi.mocked(marketDataApi.getOhlcvBars).mockResolvedValue({
      symbol: "AAPL",
      interval: "1d",
      data_completeness: "complete",
      bars: [
        {
          bar_time: "2024-01-01T00:00:00Z",
          open: "148",
          high: "152",
          low: "147",
          close: "150",
          adjusted_close: "150",
          volume: 1_000_000,
          is_closed: true,
          source: "yfinance",
        },
      ],
    });
    vi.mocked(marketDataApi.getCorporateActions).mockResolvedValue({
      items: [
        {
          id: "action-1",
          action_type: "split",
          ratio: "2",
          cash_amount: null,
          ex_date: "2024-01-01",
          announced_at: null,
        },
      ],
    });
  });

  it("renders the live quote and corporate actions once loaded", async () => {
    renderWithQueryClient(<InstrumentDetails symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("Split")).toBeInTheDocument();
    });
    expect(screen.getByText("2:1")).toBeInTheDocument();
  });

  it("toggles between candlestick and line chart modes", async () => {
    renderWithQueryClient(<InstrumentDetails symbol="AAPL" />);

    await waitFor(() => {
      expect(marketDataApi.getOhlcvBars).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: /line/i }));

    await waitFor(() => {
      expect(marketDataApi.getHistoricalPrices).toHaveBeenCalled();
    });
  });

  it("shows a message when there are no corporate actions", async () => {
    vi.mocked(marketDataApi.getCorporateActions).mockResolvedValue({
      items: [],
    });

    renderWithQueryClient(<InstrumentDetails symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText(/no corporate actions recorded/i)).toBeInTheDocument();
    });
  });
});
