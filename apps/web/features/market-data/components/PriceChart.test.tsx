import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PriceChart } from "./PriceChart";

const setDataMock = vi.fn();
const fitContentMock = vi.fn();
const addSeriesMock = vi.fn(() => ({ setData: setDataMock }));
const removeMock = vi.fn();
const applyOptionsMock = vi.fn();

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addSeries: addSeriesMock,
    remove: removeMock,
    applyOptions: applyOptionsMock,
    timeScale: () => ({ fitContent: fitContentMock }),
  })),
  LineSeries: "LineSeries",
  ColorType: { Solid: "solid" },
}));

describe("PriceChart", () => {
  it("shows an empty state when there are no points", () => {
    render(<PriceChart points={[]} />);
    expect(screen.getByText(/no historical price data available/i)).toBeInTheDocument();
  });

  it("creates a line chart and feeds it data when points are provided", () => {
    render(
      <PriceChart
        points={[
          { as_of: "2024-01-01T00:00:00Z", price: "100.5" },
          { as_of: "2024-01-02T00:00:00Z", price: "102.75" },
        ]}
      />
    );

    expect(addSeriesMock).toHaveBeenCalledWith(
      "LineSeries",
      expect.objectContaining({ color: expect.any(String) })
    );
    expect(setDataMock).toHaveBeenCalledWith([
      expect.objectContaining({ value: 100.5 }),
      expect.objectContaining({ value: 102.75 }),
    ]);
    expect(fitContentMock).toHaveBeenCalled();
  });
});
