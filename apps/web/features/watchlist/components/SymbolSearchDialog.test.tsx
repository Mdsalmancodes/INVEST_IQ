import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SymbolSearchDialog } from "./SymbolSearchDialog";

vi.mock("../../market-data/components/StockSearch", () => ({
  StockSearch: ({ onSelect }: { onSelect: (symbol: string) => void }) => (
    <button type="button" onClick={() => onSelect("AAPL")}>
      Mock StockSearch
    </button>
  ),
}));

describe("SymbolSearchDialog", () => {
  it("does not render when isOpen is false", () => {
    render(<SymbolSearchDialog isOpen={false} onClose={vi.fn()} onSelect={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the dialog with a custom title", () => {
    render(
      <SymbolSearchDialog isOpen={true} onClose={vi.fn()} onSelect={vi.fn()} title="Pick a symbol" />
    );
    expect(screen.getByText("Pick a symbol")).toBeInTheDocument();
  });

  it("calls onSelect and onClose when a symbol is picked", () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<SymbolSearchDialog isOpen={true} onClose={onClose} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("Mock StockSearch"));

    expect(onSelect).toHaveBeenCalledWith("AAPL");
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(<SymbolSearchDialog isOpen={true} onClose={onClose} onSelect={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
