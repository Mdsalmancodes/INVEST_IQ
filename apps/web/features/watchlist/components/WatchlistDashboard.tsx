"use client";

import { useState } from "react";

import { useWatchlist } from "../hooks/useWatchlists";
import { CreateWatchlistDialog } from "./CreateWatchlistDialog";
import { EditWatchlistDialog } from "./EditWatchlistDialog";
import { WatchlistCards } from "./WatchlistCards";

export interface WatchlistDashboardProps {
  onSelectWatchlist: (watchlistId: string) => void;
}

/**
 * WatchlistDashboard — the top-level component wiring WatchlistCards +
 * CreateWatchlistDialog + EditWatchlistDialog together, matching Phase
 * 3's PortfoliosPage-level composition pattern (app/dashboard/portfolios/page.tsx).
 */
export function WatchlistDashboard({ onSelectWatchlist }: WatchlistDashboardProps) {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingWatchlistId, setEditingWatchlistId] = useState<string | null>(null);

  const { data: editingWatchlist } = useWatchlist(editingWatchlistId ?? undefined);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Watchlists</h1>
        <button
          type="button"
          onClick={() => setIsCreateOpen(true)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
        >
          New Watchlist
        </button>
      </div>

      <WatchlistCards
        onSelectWatchlist={onSelectWatchlist}
        onEditWatchlist={(watchlistId) => setEditingWatchlistId(watchlistId)}
      />

      <CreateWatchlistDialog isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />

      {editingWatchlistId && editingWatchlist && (
        <EditWatchlistDialog
          watchlistId={editingWatchlistId}
          currentName={editingWatchlist.name}
          currentIsDefault={editingWatchlist.is_default}
          isOpen={true}
          onClose={() => setEditingWatchlistId(null)}
        />
      )}
    </div>
  );
}
