import type { Metadata, Viewport } from "next";

import "../styles/globals.css";

import { Providers } from "./providers";

// Placeholder production URL — this is a dev-stage project with no real
// deployed domain yet. Update once a real production URL exists; every
// openGraph/twitter absolute-URL field below derives from this one
// constant so there's a single place to change it later.
const SITE_URL = "https://investiq.app";

export const metadata: Metadata = {
  title: "INVEST IQ",
  description: "AI-powered investment intelligence platform.",
  metadataBase: new URL(SITE_URL),
  openGraph: {
    title: "INVEST IQ",
    description: "AI-powered investment intelligence platform.",
    url: SITE_URL,
    siteName: "INVEST IQ",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "INVEST IQ",
    description: "AI-powered investment intelligence platform.",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
