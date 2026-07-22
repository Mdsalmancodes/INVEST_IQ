"use client";

import { Card } from "@investiq/ui";
import {
  type CandlestickData,
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface OhlcvBarPoint {
  bar_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
}

export interface OhlcvChartProps {
  bars: OhlcvBarPoint[];
}

function toChartData(bars: OhlcvBarPoint[]): CandlestickData<Time>[] {
  return bars.map((bar) => ({
    time: (new Date(bar.bar_time).getTime() / 1000) as UTCTimestamp,
    open: Number.parseFloat(bar.open),
    high: Number.parseFloat(bar.high),
    low: Number.parseFloat(bar.low),
    close: Number.parseFloat(bar.close),
  }));
}

/**
 * OhlcvChart — candlestick chart using TradingView's lightweight-charts,
 * per Document 8 §24's roadmap: "a real price chart (TradingView
 * lightweight-charts wrapper)". Distinct from PriceChart (a simpler line
 * chart for the adjusted-close-only Historical Price API) since OHLCV
 * data supports genuine candlestick visualization.
 */
export function OhlcvChart({ bars }: OhlcvChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "rgba(100, 116, 139, 0.1)" },
        horzLines: { color: "rgba(100, 116, 139, 0.1)" },
      },
      width: containerRef.current.clientWidth,
      height: 320,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return;
    seriesRef.current.setData(toChartData(bars));
    chartRef.current.timeScale().fitContent();
  }, [bars]);

  if (bars.length === 0) {
    return (
      <Card className="flex h-80 items-center justify-center text-sm text-text-secondary">
        No OHLCV data available for this range.
      </Card>
    );
  }

  return (
    <Card className="p-2">
      <div ref={containerRef} className="w-full" />
    </Card>
  );
}
