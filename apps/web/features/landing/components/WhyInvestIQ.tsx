"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";

/**
 * AnimatedCounter — count-up-on-scroll-into-view number, used by
 * WhyInvestIQ's stat cards. Plain requestAnimationFrame easing (no new
 * dependency needed for a single-purpose count-up — matching this
 * codebase's established "small purpose-built code over a library for a
 * narrow need" precedent, e.g. Toast.tsx's own docstring).
 */
function AnimatedCounter({
  target,
  suffix = "",
  duration = 1400,
}: {
  target: number;
  suffix?: string;
  duration?: number;
}) {
  const [value, setValue] = useState(0);
  const [started, setStarted] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (started || !ref.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [started]);

  useEffect(() => {
    if (!started) return;
    let startTime: number | null = null;
    let frameId: number;

    const step = (timestamp: number) => {
      if (startTime === null) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      const eased = 1 - (1 - progress) ** 3; // ease-out cubic
      setValue(Math.round(eased * target));
      if (progress < 1) {
        frameId = requestAnimationFrame(step);
      }
    };
    frameId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frameId);
  }, [started, target, duration]);

  return (
    <span ref={ref} className="text-4xl font-bold text-primary">
      {value.toLocaleString()}
      {suffix}
    </span>
  );
}

const STATS = [
  { value: 6, suffix: "", label: "ML models in the ensemble" },
  { value: 15, suffix: "min", label: "Access token session security" },
  { value: 100, suffix: "%", label: "Explainable, SHAP-backed decisions" },
  { value: 24, suffix: "/7", label: "Real-time WebSocket streaming" },
] as const;

const REASONS = [
  {
    title: "Built on a real decision engine",
    description:
      "Not a black box — a weighted ensemble of six models with a documented Decision Engine you can inspect.",
  },
  {
    title: "Security-first architecture",
    description:
      "JWT auth with Redis-backed token blacklisting, rate limiting, and role-based access control from day one.",
  },
  {
    title: "Real-time by design",
    description:
      "WebSocket infrastructure streams quotes, predictions, and alerts the instant they change — not on a timer.",
  },
] as const;

export function WhyInvestIQ() {
  return (
    <section id="why" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-14 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Why INVEST IQ
          </h2>
        </div>

        <div className="mb-16 grid grid-cols-2 gap-6 sm:grid-cols-4">
          {STATS.map((stat) => (
            <div key={stat.label} className="flex flex-col items-center text-center">
              <AnimatedCounter target={stat.value} suffix={stat.suffix} />
              <span className="mt-2 text-sm text-text-secondary">{stat.label}</span>
            </div>
          ))}
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {REASONS.map((reason, i) => (
            <motion.div
              key={reason.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
            >
              <Card className="h-full">
                <h3 className="text-lg font-semibold text-text-primary">{reason.title}</h3>
                <p className="mt-2 text-sm text-text-secondary">{reason.description}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
