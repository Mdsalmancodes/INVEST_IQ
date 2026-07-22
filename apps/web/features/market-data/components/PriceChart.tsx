"use client";

import { Card } from "@investiq/ui";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

export interface PricePoint {
  as_of: string;
  price: string;
}

export interface PriceChartProps {
  points: PricePoint[];
}

function toChartData(points: PricePoint[]): LineData<Time>[] {
  return points.map((point) => ({
    time: (new Date(point.as_of).getTime() / 1000) as UTCTimestamp,
    value: Number.parseFloat(point.price),
  }));
}

/**
 * PriceChart — a simple adjusted-close line chart for the Historical
 * Price API, distinct from OhlcvChart's candlestick view (which needs
 * full OHLCV bars, not just a close-price series).
 */
export function PriceChart({ points }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

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
      height: 240,
    });
    const series = chart.addSeries(LineSeries, {
      color: "#6c3bff",
      lineWidth: 2,
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
    seriesRef.current.setData(toChartData(points));
    chartRef.current.timeScale().fitContent();
  }, [points]);

  if (points.length === 0) {
    return (
      <Card className="flex h-60 items-center justify-center text-sm text-text-secondary">
        No historical price data available for this range.
      </Card>
    );
  }

  return (
    <Card className="p-2">
      <div ref={containerRef} className="w-full" />
    </Card>
  );
}
