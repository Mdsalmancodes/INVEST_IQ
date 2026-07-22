import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OhlcvChart } from "./OhlcvChart";

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
  CandlestickSeries: "CandlestickSeries",
  ColorType: { Solid: "solid" },
}));

describe("OhlcvChart", () => {
  it("shows an empty state when there are no bars", () => {
    render(<OhlcvChart bars={[]} />);
    expect(screen.getByText(/no ohlcv data available/i)).toBeInTheDocument();
  });

  it("creates a candlestick chart and feeds it data when bars are provided", () => {
    render(
      <OhlcvChart
        bars={[
          { bar_time: "2024-01-01T00:00:00Z", open: "100", high: "110", low: "95", close: "105" },
          { bar_time: "2024-01-02T00:00:00Z", open: "105", high: "112", low: "100", close: "108" },
        ]}
      />
    );

    expect(addSeriesMock).toHaveBeenCalledWith(
      "CandlestickSeries",
      expect.objectContaining({ upColor: expect.any(String) })
    );
    expect(setDataMock).toHaveBeenCalledWith([
      expect.objectContaining({ open: 100, high: 110, low: 95, close: 105 }),
      expect.objectContaining({ open: 105, high: 112, low: 100, close: 108 }),
    ]);
    expect(fitContentMock).toHaveBeenCalled();
  });
});
