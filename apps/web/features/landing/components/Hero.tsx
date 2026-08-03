"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { Button } from "@investiq/ui";
import { motion } from "motion/react";

// Same next/dynamic + ssr:false bundle-size rationale as app/page.tsx's
// AnimatedBackground — AIVisualization pulls in the same heavy three.js/
// R3F/drei chunk. Deferring it here too means the Hero's text/CTA can
// render and become interactive without waiting on that chunk at all.
const AIVisualization = dynamic(
  () => import("./AIVisualization").then((m) => m.AIVisualization),
  { ssr: false }
);

/**
 * Hero — landing page opener. White+purple, Apple-level minimalism per
 * the design brief: large confident headline, one clear CTA pair, the
 * AIVisualization scene as the visual anchor instead of a stock photo.
 * Framer Motion staggers text/CTA entrance; the 3D scene mounts
 * immediately (it's cheap enough not to need its own loading gate).
 */
const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.12 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" as const } },
};

export function Hero() {
  return (
    <section className="relative overflow-hidden px-4 pt-20 pb-16 sm:pt-28 sm:pb-24">
      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={container}
          className="flex flex-col items-start gap-6 text-left"
        >
          <motion.span
            variants={item}
            className="glass rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-primary"
          >
            AI-Powered Investment Intelligence
          </motion.span>

          <motion.h1
            variants={item}
            className="text-4xl font-bold tracking-tight text-text-primary sm:text-5xl lg:text-6xl"
          >
            Invest smarter with{" "}
            <span className="bg-gradient-to-r from-primary to-[#8b5fff] bg-clip-text text-transparent">
              AI-driven
            </span>{" "}
            insight
          </motion.h1>

          <motion.p variants={item} className="max-w-xl text-lg text-text-secondary">
            INVEST IQ combines six machine-learning models, real-time sentiment analysis,
            and live market data into one dashboard — so every decision is backed by
            evidence, not guesswork.
          </motion.p>

          <motion.div variants={item} className="flex flex-wrap items-center gap-4 pt-2">
            <Link href="/register">
              <Button size="lg">Get Started Free</Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="secondary">
                Sign In
              </Button>
            </Link>
          </motion.div>

          <motion.div
            variants={item}
            className="flex items-center gap-6 pt-4 text-sm text-text-secondary"
          >
            <span>6 ML Models</span>
            <span className="h-1 w-1 rounded-full bg-text-secondary/40" />
            <span>Real-Time Data</span>
            <span className="h-1 w-1 rounded-full bg-text-secondary/40" />
            <span>Explainable AI</span>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="relative h-80 w-full sm:h-96 lg:h-[28rem]"
        >
          <AIVisualization />
        </motion.div>
      </div>
    </section>
  );
}
