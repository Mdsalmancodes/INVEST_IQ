"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";
import { useState } from "react";

import { useCorporateActions, useHistoricalPrices, useOhlcvBars } from "../hooks/useMarketData";
import { LiveQuote } from "./LiveQuote";
import { OhlcvChart } from "./OhlcvChart";
import { PriceChart } from "./PriceChart";

export interface InstrumentDetailsProps {
  symbol: string;
}

const TYPE_LABELS: Record<string, string> = {
  split: "Split",
  dividend: "Dividend",
  spinoff: "Spinoff",
};

/**
 * InstrumentDetails — wires LiveQuote, PriceChart (adjusted-close line),
 * OhlcvChart (candlestick), and a corporate actions list together for a
 * single instrument. Toggles between the line chart (Historical Price
 * API) and candlestick chart (OHLCV API) since the founder's requirement
 * names both as distinct components.
 */
export function InstrumentDetails({ symbol }: InstrumentDetailsProps) {
  const [chartMode, setChartMode] = useState<"line" | "candlestick">("candlestick");

  const { data: pricesData, isLoading: pricesLoading, isError: pricesError } = useHistoricalPrices(
    symbol
  );
  const { data: barsData, isLoading: barsLoading, isError: barsError } = useOhlcvBars(symbol);
  const {
    data: actionsData,
    isLoading: actionsLoading,
    isError: actionsError,
  } = useCorporateActions(symbol);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex flex-col gap-4"
    >
      <LiveQuote symbol={symbol} />

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setChartMode("candlestick")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            chartMode === "candlestick"
              ? "bg-primary text-white"
              : "bg-primary-50 text-text-primary"
          }`}
        >
          Candlestick
        </button>
        <button
          type="button"
          onClick={() => setChartMode("line")}
          className={`rounded-md px-3 py-1.5 text-sm font-medium ${
            chartMode === "line" ? "bg-primary text-white" : "bg-primary-50 text-text-primary"
          }`}
        >
          Line
        </button>
      </div>

      {chartMode === "candlestick" && (
        <>
          {barsLoading && (
            <Card role="status" className="h-80 animate-pulse bg-primary-50" />
          )}
          {barsError && (
            <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
              Failed to load OHLCV data.
            </Card>
          )}
          {barsData && <OhlcvChart bars={barsData.bars} />}
        </>
      )}

      {chartMode === "line" && (
        <>
          {pricesLoading && (
            <Card role="status" className="h-60 animate-pulse bg-primary-50" />
          )}
          {pricesError && (
            <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
              Failed to load historical prices.
            </Card>
          )}
          {pricesData && <PriceChart points={pricesData.points} />}
        </>
      )}

      <div>
        <h2 className="mb-2 text-lg font-semibold text-text-primary">Corporate Actions</h2>
        {actionsLoading && (
          <Card role="status" className="h-16 animate-pulse bg-primary-50" />
        )}
        {actionsError && (
          <Card role="alert" className="border-danger/40 bg-danger/5 text-danger">
            Failed to load corporate actions.
          </Card>
        )}
        {actionsData && actionsData.items.length === 0 && (
          <Card className="text-sm text-text-secondary">
            No corporate actions recorded for this instrument.
          </Card>
        )}
        {actionsData && actionsData.items.length > 0 && (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-primary-100 text-left text-text-secondary">
                  <th className="px-4 py-3 font-medium">Ex-Date</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Ratio / Amount</th>
                </tr>
              </thead>
              <tbody>
                {actionsData.items.map((action) => (
                  <tr key={action.id} className="border-b border-primary-50 last:border-0">
                    <td className="px-4 py-3">{action.ex_date}</td>
                    <td className="px-4 py-3">
                      {TYPE_LABELS[action.action_type] ?? action.action_type}
                    </td>
                    <td className="px-4 py-3">
                      {action.ratio ? `${action.ratio}:1` : action.cash_amount ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </motion.div>
  );
}
