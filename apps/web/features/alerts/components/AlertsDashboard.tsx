"use client";

import { useState } from "react";

import { AlertsList } from "./AlertsList";
import { CreateAlertDialog } from "./CreateAlertDialog";

/**
 * AlertsDashboard — the top-level component wiring AlertsList +
 * CreateAlertDialog together, matching WatchlistDashboard's composition
 * pattern (Phase 5).
 */
export function AlertsDashboard() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Alerts</h1>
        <button
          type="button"
          onClick={() => setIsCreateOpen(true)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white"
        >
          New Alert
        </button>
      </div>

      <AlertsList />

      <CreateAlertDialog isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} />
    </div>
  );
}
