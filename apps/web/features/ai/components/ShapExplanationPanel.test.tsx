import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExplainabilityResponse } from "../../../lib/ai-api";
import { ShapExplanationPanel } from "./ShapExplanationPanel";

const explainability: ExplainabilityResponse = {
  top_contributions: [
    { name: "rsi_14", value: 0.42, direction: "positive" },
    { name: "macd_histogram", value: -0.18, direction: "negative" },
  ],
  base_value: 0.1,
  method: "shap_tree_explainer",
  reasoning: "RSI and MACD suggest bullish momentum overall.",
};

describe("ShapExplanationPanel", () => {
  it("renders the reasoning text", () => {
    render(<ShapExplanationPanel explainability={explainability} />);
    expect(
      screen.getByText("RSI and MACD suggest bullish momentum overall.")
    ).toBeInTheDocument();
  });

  it("renders every feature contribution by name", () => {
    render(<ShapExplanationPanel explainability={explainability} />);
    expect(screen.getByText("rsi_14")).toBeInTheDocument();
    expect(screen.getByText("macd_histogram")).toBeInTheDocument();
  });

  it("renders the method and base value", () => {
    render(<ShapExplanationPanel explainability={explainability} />);
    expect(screen.getByText(/shap_tree_explainer/)).toBeInTheDocument();
    expect(screen.getByText(/0\.100/)).toBeInTheDocument();
  });
});
