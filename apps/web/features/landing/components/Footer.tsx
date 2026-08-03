import Link from "next/link";

/**
 * Footer — final landing section. Plain (no motion needed for a footer)
 * with real internal links only (no placeholder social/external links
 * that would 404 or point nowhere).
 */
export function Footer() {
  return (
    <footer className="border-t border-[var(--glass-border)] px-4 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 sm:flex-row">
        <span className="text-lg font-semibold text-text-primary">INVEST IQ</span>

        <nav className="flex flex-wrap items-center gap-6 text-sm text-text-secondary">
          <a href="#features" className="hover:text-text-primary">
            Features
          </a>
          <a href="#ml-models" className="hover:text-text-primary">
            ML Models
          </a>
          <a href="#faq" className="hover:text-text-primary">
            FAQ
          </a>
          <Link href="/login" className="hover:text-text-primary">
            Sign In
          </Link>
        </nav>

        <span className="text-xs text-text-secondary">
          © {new Date().getFullYear()} INVEST IQ. AI-generated signals are not financial
          advice.
        </span>
      </div>
    </footer>
  );
}
