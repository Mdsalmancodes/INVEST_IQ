import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PasswordStrengthMeter } from "./PasswordStrengthMeter";

describe("PasswordStrengthMeter", () => {
  it("renders nothing for an empty password", () => {
    render(<PasswordStrengthMeter password="" />);
    expect(screen.queryByText(/password strength/i)).not.toBeInTheDocument();
  });

  it("shows Weak for a short, low-diversity password", () => {
    render(<PasswordStrengthMeter password="aaaaaaaaaa" />);
    expect(screen.getByText(/password strength: weak/i)).toBeInTheDocument();
  });

  it("shows Strong for a long password with mixed character classes", () => {
    render(<PasswordStrengthMeter password="Str0ng!Passphrase#2026" />);
    expect(screen.getByText(/password strength: strong/i)).toBeInTheDocument();
  });

  it("has an aria-live region for accessible strength announcements", () => {
    const { container } = render(<PasswordStrengthMeter password="somepassword123" />);
    expect(container.querySelector("[aria-live='polite']")).toBeInTheDocument();
  });
});
