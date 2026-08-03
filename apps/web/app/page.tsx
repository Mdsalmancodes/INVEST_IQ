import { AnimatedBackgroundLazy } from "../features/landing/components/AnimatedBackgroundLazy";
import { FAQ } from "../features/landing/components/FAQ";
import { Features } from "../features/landing/components/Features";
import { Footer } from "../features/landing/components/Footer";
import { Hero } from "../features/landing/components/Hero";
import { LiveDashboardPreview } from "../features/landing/components/LiveDashboardPreview";
import { MLModels } from "../features/landing/components/MLModels";
import { SentimentAnalysis } from "../features/landing/components/SentimentAnalysis";
import { Testimonials } from "../features/landing/components/Testimonials";
import { WhyInvestIQ } from "../features/landing/components/WhyInvestIQ";

/**
 * Landing page — full premium redesign (White+Purple glassmorphism,
 * Stripe/Linear/Vercel-quality section composition). Replaces the Phase 1
 * skeleton card (which only verified apps/web boots + consumes
 * packages/ui) with the actual product marketing site:
 * Hero → Features → LiveDashboardPreview → WhyInvestIQ → MLModels →
 * SentimentAnalysis → Testimonials → FAQ → Footer.
 *
 * AnimatedBackground is a single fixed R3F Canvas mounted once behind
 * every section (not per-section) — cheaper than multiple WebGL contexts
 * and avoids the "too many active WebGL contexts" browser warning.
 */
export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-x-hidden">
      <AnimatedBackgroundLazy />
      <Hero />
      <Features />
      <LiveDashboardPreview />
      <WhyInvestIQ />
      <MLModels />
      <SentimentAnalysis />
      <Testimonials />
      <FAQ />
      <Footer />
    </main>
  );
}
