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

import type { MemberForecastResponse } from "../../../lib/ai-api";

export interface ForecastChartProps {
  memberForecasts: MemberForecastResponse[];
}

const SERIES_COLORS: Record<string, string> = {
  lstm: "#6c3bff",
  arima: "#10b981",
  prophet: "#f59e0b",
};

function toChartData(
  forecast: MemberForecastResponse,
  baseTime: number
): LineData<Time>[] {
  return forecast.points.map((point) => ({
    time: (baseTime + point.horizon_days * 86_400) as UTCTimestamp,
    value: point.predicted_price,
  }));
}

/**
 * ForecastChart — compares LSTM/ARIMA/Prophet's Next-Day/7-Day/30-Day
 * price forecasts on one lightweight-charts line chart, per the
 * founder's explicit "Compare its prediction with LSTM"/"Long-term
 * Forecast" instructions and the dedicated GET /api/v1/ml/forecast/
 * {symbol} endpoint's member_forecasts array (LSTM/ARIMA/Prophet only —
 * ForecastUseCase's disclosed scope, distinct from the Random Forest/
 * XGBoost/FinBERT signals shown elsewhere).
 */
export function ForecastChart({ memberForecasts }: ForecastChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

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
      height: 280,
    });
    chartRef.current = chart;

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
      seriesRefs.current.clear();
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    for (const series of seriesRefs.current.values()) {
      chart.removeSeries(series);
    }
    seriesRefs.current.clear();

    const baseTime = Math.floor(Date.now() / 1000);
    for (const forecast of memberForecasts) {
      const series = chart.addSeries(LineSeries, {
        color: SERIES_COLORS[forecast.model_family] ?? "#64748b",
        lineWidth: 2,
        title: forecast.model_family.toUpperCase(),
      });
      series.setData(toChartData(forecast, baseTime));
      seriesRefs.current.set(forecast.model_family, series);
    }
    chart.timeScale().fitContent();
  }, [memberForecasts]);

  if (memberForecasts.length === 0) {
    return (
      <Card className="flex h-72 items-center justify-center text-sm text-text-secondary">
        No forecasting models were available for this symbol.
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-2 p-2">
      <div ref={containerRef} className="w-full" />
      <div className="flex gap-4 px-4 pb-2 text-xs text-text-secondary">
        {memberForecasts.map((forecast) => (
          <span key={forecast.model_family} className="flex items-center gap-1">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: SERIES_COLORS[forecast.model_family] ?? "#64748b" }}
            />
            {forecast.model_family.toUpperCase()} ({Math.round(forecast.confidence * 100)}%)
          </span>
        ))}
      </div>
    </Card>
  );
}
