import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfidenceIndicator } from "./ConfidenceIndicator";

describe("ConfidenceIndicator", () => {
  it("renders the confidence percentage", () => {
    render(<ConfidenceIndicator confidence={0.73} />);
    expect(screen.getByText("73%")).toBeInTheDocument();
  });

  it("exposes an accessible progressbar with the correct value", () => {
    render(<ConfidenceIndicator confidence={0.5} label="Test Confidence" />);
    const progressbar = screen.getByRole("progressbar", { name: "Test Confidence" });
    expect(progressbar).toHaveAttribute("aria-valuenow", "50");
  });

  it("uses the provided label", () => {
    render(<ConfidenceIndicator confidence={0.9} label="Overall Confidence" />);
    expect(screen.getByText("Overall Confidence")).toBeInTheDocument();
  });

  it("defaults to the label 'Confidence' when none is provided", () => {
    render(<ConfidenceIndicator confidence={0.2} />);
    expect(screen.getByText("Confidence")).toBeInTheDocument();
  });
});
