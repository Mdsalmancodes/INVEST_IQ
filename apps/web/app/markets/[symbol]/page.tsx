import Link from "next/link";

import { InstrumentDetails } from "../../../features/market-data/components/InstrumentDetails";

export default async function InstrumentDetailsPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const normalizedSymbol = symbol.toUpperCase();

  return (
    <main className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-4xl">
        <Link href="/markets" className="text-sm text-primary hover:underline">
          ← Back to search
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-text-primary">{normalizedSymbol}</h1>
        <div className="mt-6">
          <InstrumentDetails symbol={normalizedSymbol} />
        </div>
      </div>
    </main>
  );
}
