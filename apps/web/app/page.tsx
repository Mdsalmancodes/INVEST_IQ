import { Button, Card } from "@investiq/ui";

/**
 * Phase 1 placeholder page — exists to verify the full stack boots and that
 * apps/web correctly consumes packages/ui (Document 2 §6.3). The real
 * landing page (hero, features, etc.) is built in Phase 5 per the roadmap
 * (Document 8 §24).
 */
export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <Card className="max-w-md text-center">
        <h1 className="mb-2 text-2xl font-semibold">INVEST IQ</h1>
        <p className="mb-6 text-sm opacity-70">
          Phase 1 foundation skeleton — full landing page arrives in Phase 5.
        </p>
        <Button>Get Started</Button>
      </Card>
    </main>
  );
}
