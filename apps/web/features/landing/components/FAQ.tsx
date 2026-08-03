"use client";

import { Card } from "@investiq/ui";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

/**
 * FAQ — accordion built with plain motion (AnimatePresence + height
 * animation), matching the exact pattern already used by
 * dashboard/layout.tsx's mobile nav and every dialog in features/* —
 * no new accordion dependency needed for this.
 */
const FAQS = [
  {
    question: "Is INVEST IQ real financial advice?",
    answer:
      "No. Recommendations are AI-generated signals for informational purposes, not licensed financial advice. Always do your own research before investing.",
  },
  {
    question: "How does the AI actually decide buy/sell/hold?",
    answer:
      "A Hybrid Decision Engine combines signals from six models (LSTM, ARIMA, Prophet, Random Forest, XGBoost, FinBERT), each weighted by historical confidence, into a single ensemble verdict with a SHAP-based explanation.",
  },
  {
    question: "Can I use this with paper (simulated) portfolios?",
    answer:
      "Yes — every portfolio can be created as paper or live, so you can test strategies risk-free before committing real capital.",
  },
  {
    question: "Is my data secure?",
    answer:
      "Authentication uses JWT access + refresh tokens with Redis-backed blacklisting, rate limiting, and role-based access control. AI infrastructure is never directly reachable by the browser — every AI call is proxied and authenticated server-side.",
  },
  {
    question: "Do I need a credit card to sign up?",
    answer: "No. Creating an account is free — get started in under a minute.",
  },
] as const;

function FAQItem({
  question,
  answer,
  isOpen,
  onToggle,
}: {
  question: string;
  answer: string;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <Card className="overflow-hidden p-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between px-6 py-4 text-left"
      >
        <span className="font-medium text-text-primary">{question}</span>
        <motion.span
          animate={{ rotate: isOpen ? 45 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-xl text-primary"
        >
          +
        </motion.span>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <p className="px-6 pb-4 text-sm text-text-secondary">{answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}

export function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <section id="faq" className="px-4 py-20">
      <div className="mx-auto max-w-3xl">
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-bold text-text-primary sm:text-4xl">
            Frequently asked questions
          </h2>
        </div>

        <div className="flex flex-col gap-3">
          {FAQS.map((faq, i) => (
            <FAQItem
              key={faq.question}
              question={faq.question}
              answer={faq.answer}
              isOpen={openIndex === i}
              onToggle={() => setOpenIndex((current) => (current === i ? null : i))}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
