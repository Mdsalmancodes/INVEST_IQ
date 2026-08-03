import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * @react-three/fiber's <Canvas> requires a real WebGL context, which
 * jsdom does not provide (see AnimatedBackground.tsx/AIVisualization.tsx,
 * both mounted by the new landing page's Hero/HomePage tree) — mocked
 * here to a plain div so this test exercises the actual page composition
 * and copy without needing a WebGL-capable test environment. This is a
 * test-only stub; the real Canvas renders normally in the browser.
 */
vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children?: React.ReactNode }) => <div data-testid="r3f-canvas">{children}</div>,
}));
vi.mock("@react-three/drei", () => ({
  Environment: () => null,
  Float: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  MeshDistortMaterial: () => null,
  Sphere: () => null,
}));

/**
 * jsdom does not implement IntersectionObserver — needed by motion's
 * `whileInView` prop (used throughout the new landing sections) and by
 * WhyInvestIQ.tsx's AnimatedCounter. A minimal stub is sufficient here:
 * this test only asserts on final rendered content, not on the actual
 * scroll-triggered animation timing.
 */
class MockIntersectionObserver implements IntersectionObserver {
  readonly root: Element | Document | null = null;
  readonly rootMargin: string = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe = () => undefined;
  unobserve = () => undefined;
  disconnect = () => undefined;
  takeRecords = () => [];
}
vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the Hero headline", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Invest smarter with AI-driven insight"
    );
  });

  it("renders the primary call-to-action linking to registration", () => {
    render(<HomePage />);
    const cta = screen.getByRole("link", { name: "Get Started Free" });
    expect(cta).toHaveAttribute("href", "/register");
  });

  it("renders every major landing section", () => {
    render(<HomePage />);
    expect(screen.getByText("Everything you need to invest with confidence")).toBeInTheDocument();
    expect(screen.getByText("Six models. One decision.")).toBeInTheDocument();
    expect(screen.getByText("Know the market's mood")).toBeInTheDocument();
    expect(screen.getByText("Frequently asked questions")).toBeInTheDocument();
  });
});
