"use client";

import { AnimatePresence, motion } from "motion/react";

import { StockSearch } from "../../market-data/components/StockSearch";

export interface SymbolSearchDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (symbol: string) => void;
  title?: string;
}

/**
 * SymbolSearchDialog — a generic modal wrapper around Phase 4's
 * StockSearch component. Kept separate from AddSymbolDialog (which also
 * performs the actual "add to this watchlist" mutation) so this dialog
 * can be reused anywhere a symbol needs to be picked, not only when
 * adding to a watchlist.
 */
export function SymbolSearchDialog({
  isOpen,
  onClose,
  onSelect,
  title = "Search for a symbol",
}: SymbolSearchDialogProps) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="symbol-search-title"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md rounded-lg bg-surface p-6 shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <h2 id="symbol-search-title" className="text-lg font-semibold text-text-primary">
            {title}
          </h2>
          <div className="mt-4">
            <StockSearch
              onSelect={(symbol) => {
                onSelect(symbol);
                onClose();
              }}
            />
          </div>
          <button
            type="button"
            onClick={onClose}
            className="mt-4 text-sm text-text-secondary hover:text-text-primary"
          >
            Cancel
          </button>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
