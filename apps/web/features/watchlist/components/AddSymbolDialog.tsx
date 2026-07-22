"use client";

import { useState } from "react";

import { ApiError } from "../../../lib/auth-api";
import { useAddWatchlistItem } from "../hooks/useWatchlists";
import { SymbolSearchDialog } from "./SymbolSearchDialog";

export interface AddSymbolDialogProps {
  watchlistId: string;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * AddSymbolDialog — wraps SymbolSearchDialog with the actual "add this
 * symbol to this watchlist" mutation, surfacing the backend's real error
 * paths (DuplicateWatchlistItemError -> 409, unknown symbol -> 404) as a
 * user-facing message rather than a silent failure.
 */
export function AddSymbolDialog({ watchlistId, isOpen, onClose }: AddSymbolDialogProps) {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const addItem = useAddWatchlistItem(watchlistId);

  const handleSelect = async (symbol: string) => {
    setErrorMessage(null);
    try {
      await addItem.mutateAsync({ symbol });
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError ? error.message : "Failed to add symbol to watchlist."
      );
    }
  };

  return (
    <>
      <SymbolSearchDialog
        isOpen={isOpen}
        onClose={onClose}
        onSelect={handleSelect}
        title="Add symbol to watchlist"
      />
      {errorMessage && (
        <div
          role="alert"
          className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-md border border-danger/40 bg-danger/5 px-4 py-2 text-sm text-danger"
        >
          {errorMessage}
        </div>
      )}
    </>
  );
}
