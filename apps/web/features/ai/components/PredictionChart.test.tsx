import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MemberSignalResponse } from "../../../lib/ai-api";
import { PredictionChart } from "./PredictionChart";

const memberSignals: MemberSignalResponse[] = [
  { model_family: "lstm", signal: 0.4, confidence: 0.7, weight: 0.2 },
  { model_family: "arima", signal: -0.2, confidence: 0.5, weight: 0.12 },
];

describe("PredictionChart", () => {
  it("shows an empty state when there are no member signals", () => {
    render(<PredictionChart memberSignals={[]} />);
    expect(screen.getByText(/no model signals available/i)).toBeInTheDocument();
  });

  it("renders every model family with its weight and confidence", () => {
    render(<PredictionChart memberSignals={memberSignals} />);
    expect(screen.getByText("LSTM")).toBeInTheDocument();
    expect(screen.getByText("ARIMA")).toBeInTheDocument();
    expect(screen.getByText(/weight 20% · confidence 70%/i)).toBeInTheDocument();
    expect(screen.getByText(/weight 12% · confidence 50%/i)).toBeInTheDocument();
  });
});
