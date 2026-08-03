"use client";

import dynamic from "next/dynamic";

// Next.js 15's App Router disallows `ssr: false` in next/dynamic() when
// called directly from a Server Component (app/page.tsx has no "use
// client" directive, since none of its own JSX needs client-side
// interactivity) — the dynamic() call itself must live inside a Client
// Component. This thin wrapper is that boundary: it exists solely so
// app/page.tsx can render <AnimatedBackgroundLazy /> without needing to
// become a Client Component itself, preserving the bundle-size benefit
// (three.js/@react-three/fiber/drei deferred out of the initial JS
// payload) that was the actual point of this fix.
export const AnimatedBackgroundLazy = dynamic(
  () => import("./AnimatedBackground").then((m) => m.AnimatedBackground),
  { ssr: false }
);
