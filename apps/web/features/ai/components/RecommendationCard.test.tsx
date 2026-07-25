import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { aiApi, type RecommendationResponse } from "../../../lib/ai-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { RecommendationCard } from "./RecommendationCard";

vi.mock("../../../lib/ai-api", () => ({
  aiApi: {
    getRecommendation: vi.fn(),
  },
}));

const recommendation: RecommendationResponse = {
  symbol: "AAPL",
  verdict: "buy",
  confidence: 0.82,
  price_forecast: 191.5,
  sentiment_score: 0.35,
  data_quality: "full",
  contributing_models: ["lstm", "arima", "random_forest"],
  explainability: {
    top_contributions: [{ name: "rsi_14", value: 0.3, direction: "positive" }],
    base_value: 0.1,
    method: "shap_tree_explainer",
    reasoning: "Strong bullish signal from technical indicators.",
  },
  member_signals: [
    { model_family: "lstm", signal: 0.4, confidence: 0.7, weight: 0.2 },
  ],
  excluded_models: ["prophet"],
  price_forecast_7d: 195.0,
  price_forecast_30d: 205.0,
};

describe("RecommendationCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state initially", () => {
    vi.mocked(aiApi.getRecommendation).mockReturnValue(new Promise(() => {}));
    renderWithQueryClient(<RecommendationCard symbol="AAPL" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders the verdict, confidence, and price forecasts once loaded", async () => {
    vi.mocked(aiApi.getRecommendation).mockResolvedValue(recommendation);
    renderWithQueryClient(<RecommendationCard symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByText("buy")).toBeInTheDocument();
    });
    expect(screen.getByText("$191.50")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText(/contributing models: lstm, arima, random_forest/i)).toBeInTheDocument();
    expect(screen.getByText(/excluded models: prophet/i)).toBeInTheDocument();
  });

  it("renders the SHAP explanation panel with the recommendation's reasoning", async () => {
    vi.mocked(aiApi.getRecommendation).mockResolvedValue(recommendation);
    renderWithQueryClient(<RecommendationCard symbol="AAPL" />);

    await waitFor(() => {
      expect(
        screen.getByText("Strong bullish signal from technical indicators.")
      ).toBeInTheDocument();
    });
  });

  it("shows an error state when the request fails", async () => {
    vi.mocked(aiApi.getRecommendation).mockRejectedValue(new Error("Network error"));
    renderWithQueryClient(<RecommendationCard symbol="AAPL" />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(/failed to load recommendation/i);
  });
});
