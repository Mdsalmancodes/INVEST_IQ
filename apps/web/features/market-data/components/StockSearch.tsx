"use client";

import { Card } from "@investiq/ui";
import { useEffect, useState } from "react";

import { useInstrumentSearch } from "../hooks/useMarketData";


export interface StockSearchProps {
  onSelect: (instrument: {
    id: string;
    symbol: string;
    name: string;
  }) => void;
}

/**
 * StockSearch — debounced instrument search backed by GET
 * /api/v1/instruments/search (per Document 4's frozen catalog entry;
 * added to the backend in this session since a search box has no
 * function without a search endpoint to call).
 */
export function StockSearch({ onSelect }: StockSearchProps) {
  const [inputValue, setInputValue] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(inputValue), 300);
    return () => clearTimeout(timer);
  }, [inputValue]);

const { data, isLoading, isError } = useInstrumentSearch(debouncedQuery);
if (data) {
  console.log("API DATA FULL:", data);
}

const instrumentsToShow =
  debouncedQuery.length > 0
    ? (Array.isArray(data) ? data : data?.items ?? [])
    : [];

  return (
  <div className="relative w-full max-w-md">

    {/* ✅ INPUT */}
    <input
      id="stock-search"
      type="text"
      placeholder="Search by symbol or name (e.g. AAPL)"
      value={inputValue}
      onChange={(e) => setInputValue(e.target.value)}
      className="h-11 w-full rounded-md border border-primary-100 bg-surface px-3 text-text-primary"
    />

    {/* ✅ 🔥 PUT YOUR CODE HERE */}
    {debouncedQuery.length > 0 && (
      <Card className="absolute z-10 mt-1 w-full p-0">
        
        {isLoading && (
          <p className="p-3 text-sm text-text-secondary">Searching…</p>
        )}

        {isError && (
          <p className="p-3 text-sm text-danger">Search failed.</p>
        )}

        {!isLoading && instrumentsToShow.length === 0 && (
          <p className="p-3 text-sm text-text-secondary">
            No matching instruments found.
          </p>
        )}

        {instrumentsToShow.length > 0 && (
          <ul className="max-h-64 overflow-y-auto">
            {instrumentsToShow.map((instrument) => (
              <li key={instrument.symbol}>
                <button
                  type="button"
                  onClick={() => {
                    console.log("SELECTED:", instrument); 
                    onSelect(instrument);
                    setInputValue("");
                    setDebouncedQuery("");
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 hover:bg-primary-50"
                >
                  <span>{instrument.symbol}</span>
                  <span>{instrument.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

      </Card>
    )}

  </div>
);
}