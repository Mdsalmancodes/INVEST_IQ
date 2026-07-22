import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("renders its children", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("applies the primary variant by default", () => {
    render(<Button>Default</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-primary");
  });

  it("supports asChild composition via Radix Slot", () => {
    render(
      <Button asChild>
        <a href="/dashboard">Go</a>
      </Button>
    );
    const link = screen.getByRole("link", { name: "Go" });
    expect(link).toHaveAttribute("href", "/dashboard");
  });

  it("meets the 44px minimum touch target at default size (Document 2 §6.1a)", () => {
    render(<Button>Tap target</Button>);
    expect(screen.getByRole("button")).toHaveClass("h-11");
  });
});
