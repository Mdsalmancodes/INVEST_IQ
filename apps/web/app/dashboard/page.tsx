import { redirect } from "next/navigation";

/**
 * /dashboard now redirects to the real Portfolio Dashboard (Phase 3).
 * Was a placeholder ("Dashboard — coming in a later phase") through
 * Phase 2, whose only job was giving the login-success redirect and
 * protected-route middleware a real target to verify against — now that
 * Phase 3 has built the actual dashboard, this route forwards there
 * rather than staying a dead end.
 */
export default function DashboardPage() {
  redirect("/dashboard/portfolios");
}
