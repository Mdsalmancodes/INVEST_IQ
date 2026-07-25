import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MemberForecastResponse } from "../../../lib/ai-api";
import { ForecastChart } from "./ForecastChart";

const setDataMock = vi.fn();
const fitContentMock = vi.fn();
const addSeriesMock = vi.fn(() => ({ setData: setDataMock }));
const removeSeriesMock = vi.fn();
const removeMock = vi.fn();
const applyOptionsMock = vi.fn();

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: addSeriesMock,
    removeSeries: removeSeriesMock,
    remove: removeMock,
    applyOptions: applyOptionsMock,
    timeScale: () => ({ fitContent: fitContentMock }),
  })),
  LineSeries: "LineSeries",
  ColorType: { Solid: "solid" },
}));

const memberForecasts: MemberForecastResponse[] = [
  {
    model_family: "lstm",
    points: [
      { horizon_days: 1, predicted_price: 150, lower_bound: 145, upper_bound: 155 },
      { horizon_days: 7, predicted_price: 155, lower_bound: 148, upper_bound: 162 },
      { horizon_days: 30, predicted_price: 165, lower_bound: 150, upper_bound: 180 },
    ],
    confidence: 0.72,
    data_quality: "full",
  },
  {
    model_family: "arima",
    points: [
      { horizon_days: 1, predicted_price: 148, lower_bound: 144, upper_bound: 152 },
      { horizon_days: 7, predicted_price: 150, lower_bound: 143, upper_bound: 157 },
      { horizon_days: 30, predicted_price: 152, lower_bound: 140, upper_bound: 164 },
    ],
    confidence: 0.65,
    data_quality: "full",
  },
];

describe("ForecastChart", () => {
  it("shows an empty state when there are no member forecasts", () => {
    render(<ForecastChart memberForecasts={[]} />);
    expect(screen.getByText(/no forecasting models were available/i)).toBeInTheDocument();
  });

  it("adds one line series per model family and feeds it data", () => {
    render(<ForecastChart memberForecasts={memberForecasts} />);

    expect(addSeriesMock).toHaveBeenCalledTimes(2);
    expect(setDataMock).toHaveBeenCalledTimes(2);
    expect(fitContentMock).toHaveBeenCalled();
  });

  it("renders a legend entry with confidence for each model family", () => {
    render(<ForecastChart memberForecasts={memberForecasts} />);
    expect(screen.getByText(/LSTM \(72%\)/)).toBeInTheDocument();
    expect(screen.getByText(/ARIMA \(65%\)/)).toBeInTheDocument();
  });
});
