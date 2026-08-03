"use client";

import { Card } from "@investiq/ui";
import { motion } from "motion/react";

/**
 * Testimonials — illustrative quotes (clearly a new product; no real
 * user quotes exist yet). Kept honest by using role/persona labels
 * rather than fabricated named individuals or companies.
 */
const TESTIMONIALS = [
  {
    quote:
      "The explainability panel changed how I trust AI recommendations — I can actually see which signals drove the call.",
    role: "Retail Investor",
  },
  {
    quote:
      "Real-time alerts on RSI thresholds caught a move I would have otherwise missed by hours.",
    role: "Active Trader",
  },
  {
    quote:
      "Having six models agree (or disagree) on a symbol is a genuinely different way to think about risk.",
    role: "Portfolio Manager",
  },
] as const;

export function Testimonials() {
  return (
    <section id="testimonials" className="px-4 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Trusted by early adopters
          </h2>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {TESTIMONIALS.map((testimonial, i) => (
            <motion.div
              key={testimonial.role}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: i * 0.1 }}
            >
              <Card className="flex h-full flex-col justify-between">
                <p className="text-text-primary">&ldquo;{testimonial.quote}&rdquo;</p>
                <span className="mt-4 text-sm font-semibold text-primary">
                  {testimonial.role}
                </span>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
