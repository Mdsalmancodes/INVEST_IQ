import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { marketDataApi } from "../../../lib/market-data-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { LiveQuote } from "./LiveQuote";
import { useRealtimeConnection } from "../../realtime/hooks/useRealtimeConnection";
import type { RealtimeEnvelope } from "../../realtime/hooks/useRealtimeConnection";

vi.mock("../../../lib/market-data-api", () => ({
  marketDataApi: {
    getCurrentPrice: vi.fn(),
  },
}));

type MessageListener = (envelope: RealtimeEnvelope) => void;
let capturedListener: MessageListener | undefined;

vi.mock("../../realtime/hooks/useRealtimeConnection", () => ({
  useRealtimeConnection: vi.fn(),
}));

function mockRealtimeConnection(): void {
  capturedListener = undefined;
  vi.mocked(useRealtimeConnection).mockReturnValue({
    connectionState: "connected",
    subscribe: (_topic: string, listener: MessageListener) => {
      capturedListener = listener;
      return () => {};
    },
  });
}

describe("LiveQuote", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRealtimeConnection();
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

  it("updates the displayed price when a live quote tick arrives over the WebSocket", async () => {
    vi.mocked(marketDataApi.getCurrentPrice).mockResolvedValue({
      symbol: "AAPL",
      price: "150.00",
      previous_close: "145.00",
      source: "yfinance",
      is_stale_fallback: false,
    });

    renderWithQueryClient(<LiveQuote symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText("$150.00")).toBeInTheDocument();
    });

    // Simulate the server pushing a fresh quote tick over the shared
    // WebSocket connection (MarketDataStreamingService's own payload
    // shape) — capturedListener is the exact callback LiveQuote
    // registered via useRealtimeConnection().subscribe("quote:AAPL", ...).
    expect(capturedListener).toBeDefined();
    capturedListener?.({
      type: "quote",
      topic: "quote:AAPL",
      data: {
        symbol: "AAPL",
        price: "155.50",
        previous_close: "145.00",
        is_stale_fallback: false,
      },
    });

    await waitFor(() => {
      expect(screen.getByText("$155.50")).toBeInTheDocument();
    });
  });
});
