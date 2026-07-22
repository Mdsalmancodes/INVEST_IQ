"use client";

import { Card } from "@investiq/ui";
import { useEffect, useState } from "react";

import { useInstrumentSearch } from "../hooks/useMarketData";

export interface StockSearchProps {
  onSelect: (symbol: string) => void;
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

  return (
    <div className="relative w-full max-w-md">
      <label htmlFor="stock-search" className="sr-only">
        Search for a stock
      </label>
      <input
        id="stock-search"
        type="text"
        placeholder="Search by symbol or name (e.g. AAPL)"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        className="h-11 w-full rounded-md border border-primary-100 bg-surface px-3 text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        autoComplete="off"
      />

      {debouncedQuery.length > 0 && (
        <Card className="absolute z-10 mt-1 w-full p-0">
          {isLoading && (
            <p role="status" className="p-3 text-sm text-text-secondary">
              Searching…
            </p>
          )}
          {isError && (
            <p role="alert" className="p-3 text-sm text-danger">
              Search failed. Please try again.
            </p>
          )}
          {data && data.items.length === 0 && (
            <p className="p-3 text-sm text-text-secondary">No matching instruments found.</p>
          )}
          {data && data.items.length > 0 && (
            <ul className="max-h-64 overflow-y-auto">
              {data.items.map((instrument) => (
                <li key={instrument.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(instrument.symbol);
                      setInputValue("");
                      setDebouncedQuery("");
                    }}
                    className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-primary-50"
                  >
                    <span className="font-medium text-text-primary">{instrument.symbol}</span>
                    <span className="text-sm text-text-secondary">{instrument.name}</span>
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
