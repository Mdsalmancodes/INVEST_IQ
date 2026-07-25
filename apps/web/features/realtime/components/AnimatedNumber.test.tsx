import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AnimatedNumber } from "./AnimatedNumber";

/**
 * AnimatedNumber tests — verifies the primitive's OWN behavior in
 * isolation (previously only exercised indirectly through the 6
 * dashboard components that consume it, e.g. LiveQuote/
 * PortfolioSummaryCards). Does not assert on motion's internal easing
 * curve/timing (that's motion's own well-tested responsibility) — only
 * on this component's observable contract: it renders the formatted
 * value, and re-renders (eventually) with a new formatted value when
 * `value` changes.
 */
describe("AnimatedNumber", () => {
  it("renders the formatted initial value on first mount", () => {
    render(<AnimatedNumber value={150} format={(n) => `$${n.toFixed(2)}`} />);
    expect(screen.getByText("$150.00")).toBeInTheDocument();
  });

  it("uses the identity format by default when none is provided", () => {
    render(<AnimatedNumber value={42} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("eventually renders the new formatted value after value changes", async () => {
    const { rerender } = render(
      <AnimatedNumber value={100} format={(n) => n.toFixed(0)} durationSeconds={0.01} />
    );
    expect(screen.getByText("100")).toBeInTheDocument();

    rerender(<AnimatedNumber value={200} format={(n) => n.toFixed(0)} durationSeconds={0.01} />);

    // The animation transitions through intermediate values before
    // settling at 200 — poll until the final value is reached rather
    // than asserting on any single intermediate frame.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("applies the provided className to the rendered element", () => {
    render(<AnimatedNumber value={5} className="text-success" />);
    expect(screen.getByText("5")).toHaveClass("text-success");
  });
});
