"use client";

import { useState } from "react";

import { NotificationPreferencesForm } from "./NotificationPreferencesForm";
import { NotificationsList } from "./NotificationsList";

/**
 * NotificationsDashboard — the top-level component wiring NotificationsList
 * + NotificationPreferencesForm together, matching
 * AlertsDashboard/WatchlistDashboard's composition pattern.
 */
export function NotificationsDashboard() {
  const [showPreferences, setShowPreferences] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">Notifications</h1>
        <button
          type="button"
          onClick={() => setShowPreferences((prev) => !prev)}
          className="rounded-md border border-primary-100 px-4 py-2 text-sm font-medium text-primary"
        >
          {showPreferences ? "Hide Preferences" : "Preferences"}
        </button>
      </div>

      {showPreferences && (
        <div className="glass rounded-lg p-4">
          <NotificationPreferencesForm />
        </div>
      )}

      <NotificationsList />
    </div>
  );
}
