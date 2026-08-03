"use client";

import { useState } from "react";

import { MagneticButton } from "../../dashboard-shell/components/MagneticButton";
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
        <MagneticButton onClick={() => setIsCreateOpen(true)}>New Watchlist</MagneticButton>
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
