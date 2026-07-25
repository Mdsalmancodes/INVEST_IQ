import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { aiApi, type PredictionHistoryResponse } from "../../../lib/ai-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { PredictionHistory } from "./PredictionHistory";

vi.mock("../../../lib/ai-api", () => ({
  aiApi: {
    getPredictionHistory: vi.fn(),
  },
}));

const historyWithItems: PredictionHistoryResponse = {
  symbol: "AAPL",
  items: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      symbol: "AAPL",
      ensemble_price: 191.5,
      ensemble_confidence: 0.82,
      data_quality: "full",
      created_at: "2024-06-01T12:00:00Z",
      actual_price: null,
    },
  ],
};

describe("PredictionHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(aiApi.getPredictionHistory).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<PredictionHistory symbol="AAPL" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("shows an empty state when there is no history", async () => {
    vi.mocked(aiApi.getPredictionHistory).mockResolvedValue({ symbol: "AAPL", items: [] });
    renderWithQueryClient(<PredictionHistory symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText(/no prediction history yet for aapl/i)).toBeInTheDocument();
    });
  });

  it("renders a row for each prediction run, with '—' for a missing actual price", async () => {
    vi.mocked(aiApi.getPredictionHistory).mockResolvedValue(historyWithItems);
    renderWithQueryClient(<PredictionHistory symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText("$191.50")).toBeInTheDocument();
    });
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(aiApi.getPredictionHistory).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<PredictionHistory symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
