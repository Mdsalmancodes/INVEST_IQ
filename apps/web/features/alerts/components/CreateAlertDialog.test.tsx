import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { alertsApi } from "../../../lib/alerts-api";
import { renderWithQueryClient } from "../../portfolio/test-utils";
import { CreateAlertDialog } from "./CreateAlertDialog";

vi.mock("../../../lib/alerts-api", () => ({
  alertsApi: {
    createAlert: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("CreateAlertDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    renderWithQueryClient(<CreateAlertDialog isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a validation error for an empty symbol", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateAlertDialog isOpen={true} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByText(/symbol is required/i)).toBeInTheDocument();
    expect(alertsApi.createAlert).not.toHaveBeenCalled();
  });

  it("shows a validation error for an empty threshold", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<CreateAlertDialog isOpen={true} onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/^symbol$/i), "AAPL");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByText(/threshold is required/i)).toBeInTheDocument();
    expect(alertsApi.createAlert).not.toHaveBeenCalled();
  });

  it("calls onClose and onCreated on a successful submit", async () => {
    vi.mocked(alertsApi.createAlert).mockResolvedValue({
      id: "a1",
      user_id: "u1",
      instrument_id: "i1",
      symbol: "AAPL",
      condition_type: "price_above",
      threshold: "150",
      is_recurring: false,
      cooldown_minutes: 0,
      is_active: true,
      triggered_at: null,
      created_at: "2026-01-01T00:00:00Z",
    });
    const onClose = vi.fn();
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(
      <CreateAlertDialog isOpen={true} onClose={onClose} onCreated={onCreated} />
    );

    await user.type(screen.getByLabelText(/^symbol$/i), "aapl");
    await user.type(screen.getByLabelText(/^threshold$/i), "150");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await vi.waitFor(() => {
      expect(alertsApi.createAlert).toHaveBeenCalledWith({
        symbol: "AAPL",
        condition_type: "price_above",
        threshold: "150",
        is_recurring: false,
        cooldown_minutes: 0,
      });
    });
    expect(onCreated).toHaveBeenCalledWith("a1");
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a server error message when creation fails", async () => {
    vi.mocked(alertsApi.createAlert).mockRejectedValue(new Error("Request failed"));
    const user = userEvent.setup();
    renderWithQueryClient(<CreateAlertDialog isOpen={true} onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/^symbol$/i), "AAPL");
    await user.type(screen.getByLabelText(/^threshold$/i), "150");
    await user.click(screen.getByRole("button", { name: /^create$/i }));

    expect(await screen.findByText(/failed to create alert/i)).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<CreateAlertDialog isOpen={true} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
