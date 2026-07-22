import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { portfolioApi } from "../../../lib/portfolio-api";
import { renderWithQueryClient } from "../test-utils";
import { AddTransactionDialog } from "./AddTransactionDialog";

vi.mock("../../../lib/portfolio-api", () => ({
  portfolioApi: {
    addTransaction: vi.fn(),
  },
}));

vi.mock("../../../store/auth-store", () => ({
  useAuthStore: { getState: () => ({ accessToken: "fake-token" }) },
}));

describe("AddTransactionDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    renderWithQueryClient(
      <AddTransactionDialog portfolioId="p1" isOpen={false} onClose={vi.fn()} />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows quantity and price fields for a buy transaction (the default type)", () => {
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByLabelText(/quantity/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/price per share/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/split ratio/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/cash amount/i)).not.toBeInTheDocument();
  });

  it("shows only splitRatio (no quantity/price) when split is selected", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText(/transaction type/i), "split");

    expect(screen.getByLabelText(/split ratio/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^quantity$/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/price per share/i)).not.toBeInTheDocument();
  });

  it("shows only cashAmount (no instrument) when deposit is selected", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText(/transaction type/i), "deposit");

    expect(screen.getByLabelText(/cash amount/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/instrument id/i)).not.toBeInTheDocument();
  });

  it("shows only quantity (no price) when transfer_out is selected", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText(/transaction type/i), "transfer_out");

    expect(screen.getByLabelText(/instrument id/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^quantity$/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/price per share/i)).not.toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("submits a valid buy transaction", async () => {
    vi.mocked(portfolioApi.addTransaction).mockResolvedValue({
      id: "tx-1",
      portfolio_id: "p1",
      instrument_id: "11111111-1111-1111-1111-111111111111",
      type: "buy",
      quantity: "10",
      price: "100",
      fees: "0",
      split_ratio: null,
      related_portfolio_id: null,
      cash_amount: null,
      executed_at: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    });
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWithQueryClient(<AddTransactionDialog portfolioId="p1" isOpen={true} onClose={onClose} />);

    await user.type(screen.getByLabelText(/executed at/i), "2026-01-01T10:00");
    await user.type(screen.getByLabelText(/instrument id/i), "11111111-1111-1111-1111-111111111111");
    await user.type(screen.getByLabelText(/^quantity$/i), "10");
    await user.type(screen.getByLabelText(/price per share/i), "100");
    await user.click(screen.getByRole("button", { name: /add transaction/i }));

    await vi.waitFor(() => {
      expect(portfolioApi.addTransaction).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({ type: "buy", quantity: "10", price: "100" })
      );
    });
    expect(onClose).toHaveBeenCalled();
  });
});
