import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { aiApi, type SentimentAnalysisResponse } from "../../../lib/ai-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { SentimentDashboard } from "./SentimentDashboard";

vi.mock("../../../lib/ai-api", () => ({
  aiApi: {
    analyzeSentiment: vi.fn(),
  },
}));

const response: SentimentAnalysisResponse = {
  symbol: "AAPL",
  per_item_scores: [
    { label: "positive", confidence: 0.9, source_text: "Great quarterly earnings." },
  ],
  aggregate_label: "positive",
  aggregate_confidence: 0.6,
  aggregate_article_count: 1,
};

describe("SentimentDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("disables the analyze button until text is entered", () => {
    renderWithQueryClient(<SentimentDashboard symbol="AAPL" />);
    expect(screen.getByRole("button", { name: /analyze sentiment/i })).toBeDisabled();
  });

  it("submits entered text and renders the aggregate result", async () => {
    vi.mocked(aiApi.analyzeSentiment).mockResolvedValue(response);
    const user = userEvent.setup();

    renderWithQueryClient(<SentimentDashboard symbol="AAPL" />);

    await user.type(
      screen.getByLabelText(/news or social text to analyze/i),
      "Great quarterly earnings."
    );
    await user.click(screen.getByRole("button", { name: /analyze sentiment/i }));

    await waitFor(() => {
      expect(screen.getAllByText("positive").length).toBeGreaterThan(0);
    });
    expect(aiApi.analyzeSentiment).toHaveBeenCalledWith({
      symbol: "AAPL",
      texts: ["Great quarterly earnings."],
    });
    expect(screen.getByText("1 item(s) analyzed")).toBeInTheDocument();
  });

  it("shows an error message when analysis fails", async () => {
    vi.mocked(aiApi.analyzeSentiment).mockRejectedValue(new Error("Network error"));
    const user = userEvent.setup();

    renderWithQueryClient(<SentimentDashboard symbol="AAPL" />);
    await user.type(screen.getByLabelText(/news or social text to analyze/i), "Some text.");
    await user.click(screen.getByRole("button", { name: /analyze sentiment/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
