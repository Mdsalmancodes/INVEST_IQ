import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  aiApi,
  type ForecastResponse,
  type ModelStatusResponse,
  type RecommendationResponse,
} from "../../../lib/ai-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { AIDashboard } from "./AIDashboard";

vi.mock("../../../lib/ai-api", () => ({
  aiApi: {
    getRecommendation: vi.fn(),
    getForecast: vi.fn(),
    analyzeSentiment: vi.fn(),
    getPredictionHistory: vi.fn(),
    getModelStatus: vi.fn(),
  },
}));

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({ setData: vi.fn() })),
    removeSeries: vi.fn(),
    remove: vi.fn(),
    applyOptions: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
  })),
  LineSeries: "LineSeries",
  ColorType: { Solid: "solid" },
}));

const recommendation: RecommendationResponse = {
  symbol: "AAPL",
  verdict: "hold",
  confidence: 0.5,
  price_forecast: 150,
  sentiment_score: 0.0,
  data_quality: "full",
  contributing_models: ["lstm"],
  explainability: {
    top_contributions: [],
    base_value: 0,
    method: "shap_tree_explainer",
    reasoning: "Mixed signals.",
  },
  member_signals: [{ model_family: "lstm", signal: 0.0, confidence: 0.5, weight: 0.2 }],
  excluded_models: [],
  price_forecast_7d: 151,
  price_forecast_30d: 152,
};

const forecast: ForecastResponse = { symbol: "AAPL", member_forecasts: [], excluded_models: [] };
const modelStatus: ModelStatusResponse = {
  families: [
    { family: "lstm", active_version: null, version_count: 0 },
    { family: "arima", active_version: null, version_count: 0 },
    { family: "prophet", active_version: null, version_count: 0 },
    { family: "random_forest", active_version: null, version_count: 0 },
    { family: "xgboost", active_version: null, version_count: 0 },
    { family: "finbert", active_version: null, version_count: 0 },
  ],
};

describe("AIDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(aiApi.getModelStatus).mockResolvedValue(modelStatus);
  });

  it("shows a prompt to enter a symbol before any symbol is submitted", () => {
    renderWithQueryClient(<AIDashboard />);
    expect(
      screen.getByText(/enter a symbol above to see ai-generated recommendations/i)
    ).toBeInTheDocument();
  });

  it("fetches and renders the recommendation once a symbol is submitted", async () => {
    vi.mocked(aiApi.getRecommendation).mockResolvedValue(recommendation);
    vi.mocked(aiApi.getForecast).mockResolvedValue(forecast);
    vi.mocked(aiApi.getPredictionHistory).mockResolvedValue({ symbol: "AAPL", items: [] });

    const user = userEvent.setup();
    renderWithQueryClient(<AIDashboard />);

    await user.type(screen.getByLabelText(/symbol/i), "aapl");
    await user.click(screen.getByRole("button", { name: /analyze/i }));

    await waitFor(() => {
      expect(screen.getByText("hold")).toBeInTheDocument();
    });
    expect(aiApi.getRecommendation).toHaveBeenCalledWith("AAPL");
  });

  it("always renders the model status panel for all 6 required families", async () => {
    renderWithQueryClient(<AIDashboard />);

    await waitFor(() => {
      expect(screen.getByText("Model Status")).toBeInTheDocument();
    });
    expect(screen.getByText("LSTM")).toBeInTheDocument();
    expect(screen.getByText("FinBERT")).toBeInTheDocument();
  });
});
