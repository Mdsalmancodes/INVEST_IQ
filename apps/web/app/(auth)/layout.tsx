/**
 * (auth) route group layout — Document 2 §5.2. Client-rendered (CSR),
 * no SEO need per §6.1's rendering strategy table. Shared centered card
 * shell for all auth pages, White+Purple branding (Document 2 §6.3).
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <span className="text-2xl font-bold text-primary">INVEST IQ</span>
        </div>
        <div className="rounded-xl border border-primary-100 bg-surface p-8 shadow-sm">
          {children}
        </div>
      </div>
    </main>
  );
}
