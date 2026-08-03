"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";

import { authApi } from "../../lib/auth-api";
import { useAuthStore } from "../../store/auth-store";

/**
 * Shared dashboard navigation shell — closes the standing known issue
 * (carried since Phase 5's own recommendation, re-confirmed through
 * Phase 9) that every /dashboard/* route was reachable only by direct
 * URL or a link from wherever a nav shell would eventually place them.
 * Each child page keeps its own existing per-page auth guard (this
 * layout does not replace those, it just wraps them with a consistent
 * nav — no page's redirect-to-login/loading behavior changes).
 *
 * Glassmorphism polish pass: sticky translucent/blurred header (.glass
 * utility, globals.css), a mobile hamburger menu (the original 5-link +
 * logout row had no responsive handling and would overflow below the
 * md breakpoint), and a fade/slide page transition on route change using
 * the existing `motion` dependency (matching the same AnimatePresence +
 * motion.div pattern already used by every dialog/toast in features/*).
 */
const NAV_ITEMS = [
  { href: "/dashboard/portfolios", label: "Portfolios" },
  { href: "/dashboard/watchlists", label: "Watchlists" },
  { href: "/dashboard/ai", label: "AI Insights" },
  { href: "/dashboard/alerts", label: "Alerts" },
  { href: "/dashboard/notifications", label: "Notifications" },
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const accessToken = useAuthStore((state) => state.accessToken);
  const clearSession = useAuthStore((state) => state.clearSession);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    if (accessToken) {
      try {
        await authApi.logoutCurrentSession(accessToken);
      } catch {
        // Best-effort — still clear the local session below even if the
        // server-side blacklist call fails (e.g. token already expired).
      }
    }
    clearSession();
    router.push("/login");
  };

  const navLinkClassName = (href: string, isMobile = false) => {
    const isActive = pathname?.startsWith(href);
    const base = isMobile
      ? "block rounded-md px-3 py-2.5 text-sm font-medium transition-colors"
      : "rounded-md px-3 py-2 text-sm font-medium transition-colors";
    return `${base} ${
      isActive
        ? "bg-primary/10 text-primary"
        : "text-text-primary/70 hover:bg-primary/5 hover:text-text-primary"
    }`;
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="glass sticky top-0 z-40 rounded-none border-x-0 border-t-0">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/dashboard" className="text-lg font-semibold text-text-primary">
            INVEST IQ
          </Link>

          {/* Desktop nav — hidden below md, matching Document 2 §6.1a's
              mobile-first breakpoint scale (md: 768px). */}
          <nav className="hidden items-center gap-1 md:flex">
            {NAV_ITEMS.map((item) => (
              <Link key={item.href} href={item.href} className={navLinkClassName(item.href)}>
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="hidden md:block">
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md px-3 py-2 text-sm font-medium text-text-primary/70 transition-colors hover:bg-primary/5 hover:text-text-primary"
            >
              Log out
            </button>
          </div>

          {/* Mobile menu toggle — visible only below md. */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
            className="flex h-11 w-11 items-center justify-center rounded-md text-text-primary md:hidden"
          >
            <motion.span
              animate={{ rotate: mobileMenuOpen ? 45 : 0, y: mobileMenuOpen ? 6 : 0 }}
              className="absolute block h-0.5 w-5 bg-current"
            />
            <motion.span
              animate={{ opacity: mobileMenuOpen ? 0 : 1 }}
              className="absolute block h-0.5 w-5 bg-current"
            />
            <motion.span
              animate={{ rotate: mobileMenuOpen ? -45 : 0, y: mobileMenuOpen ? -6 : 0 }}
              className="absolute block h-0.5 w-5 bg-current"
            />
          </button>
        </div>

        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.nav
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden border-t border-[var(--glass-border)] md:hidden"
            >
              <div className="flex flex-col gap-1 px-4 py-3">
                {NAV_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={navLinkClassName(item.href, true)}
                  >
                    {item.label}
                  </Link>
                ))}
                <button
                  type="button"
                  onClick={() => {
                    setMobileMenuOpen(false);
                    void handleLogout();
                  }}
                  className="block rounded-md px-3 py-2.5 text-left text-sm font-medium text-text-primary/70 hover:bg-primary/5 hover:text-text-primary"
                >
                  Log out
                </button>
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>

      <motion.main
        key={pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
      >
        {children}
      </motion.main>
    </div>
  );
}
