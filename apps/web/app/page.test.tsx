import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the INVEST IQ heading", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "INVEST IQ" })).toBeInTheDocument();
  });

  it("renders the Get Started button from @investiq/ui", () => {
    render(<HomePage />);
    expect(screen.getByRole("button", { name: "Get Started" })).toBeInTheDocument();
  });
});
