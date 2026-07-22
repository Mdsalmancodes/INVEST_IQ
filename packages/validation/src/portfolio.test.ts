import { describe, expect, it } from "vitest";

import {
  addTransactionSchema,
  createPortfolioSchema,
  decimalStringSchema,
  positiveDecimalStringSchema,
  updatePortfolioSchema,
} from "./portfolio";

describe("decimalStringSchema", () => {
  const schema = decimalStringSchema("Amount");

  it("accepts a plain integer string", () => {
    expect(schema.safeParse("100").success).toBe(true);
  });

  it("accepts a decimal string", () => {
    expect(schema.safeParse("100.50").success).toBe(true);
  });

  it("accepts a negative decimal string", () => {
    expect(schema.safeParse("-50.25").success).toBe(true);
  });

  it("rejects a non-numeric string", () => {
    expect(schema.safeParse("abc").success).toBe(false);
  });

  it("rejects an empty string", () => {
    expect(schema.safeParse("").success).toBe(false);
  });

  it("rejects a value with two decimal points", () => {
    expect(schema.safeParse("1.2.3").success).toBe(false);
  });
});

describe("positiveDecimalStringSchema", () => {
  const schema = positiveDecimalStringSchema("Quantity");

  it("accepts a positive value", () => {
    expect(schema.safeParse("10").success).toBe(true);
  });

  it("rejects zero", () => {
    expect(schema.safeParse("0").success).toBe(false);
  });

  it("rejects a negative value", () => {
    expect(schema.safeParse("-5").success).toBe(false);
  });
});

describe("createPortfolioSchema", () => {
  it("accepts a valid payload with defaults", () => {
    const result = createPortfolioSchema.safeParse({ name: "Retirement" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.baseCurrency).toBe("USD");
      expect(result.data.isPaper).toBe(true);
    }
  });

  it("rejects an empty name", () => {
    expect(createPortfolioSchema.safeParse({ name: "" }).success).toBe(false);
  });

  it("rejects an unsupported currency code", () => {
    const result = createPortfolioSchema.safeParse({ name: "P", baseCurrency: "XYZ" });
    expect(result.success).toBe(false);
  });
});

describe("updatePortfolioSchema", () => {
  it("requires both name and baseCurrency", () => {
    const result = updatePortfolioSchema.safeParse({ name: "New Name", baseCurrency: "EUR" });
    expect(result.success).toBe(true);
  });
});

describe("addTransactionSchema", () => {
  it("accepts a valid buy transaction", () => {
    const result = addTransactionSchema.safeParse({
      type: "buy",
      executedAt: "2026-01-01T00:00:00Z",
      instrumentId: "11111111-1111-1111-1111-111111111111",
      quantity: "10",
      price: "150.50",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a buy transaction missing quantity", () => {
    const result = addTransactionSchema.safeParse({
      type: "buy",
      executedAt: "2026-01-01T00:00:00Z",
      instrumentId: "11111111-1111-1111-1111-111111111111",
      price: "150.50",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a buy transaction missing instrumentId", () => {
    const result = addTransactionSchema.safeParse({
      type: "buy",
      executedAt: "2026-01-01T00:00:00Z",
      quantity: "10",
      price: "150.50",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid split transaction without quantity/price", () => {
    const result = addTransactionSchema.safeParse({
      type: "split",
      executedAt: "2026-01-01T00:00:00Z",
      instrumentId: "11111111-1111-1111-1111-111111111111",
      splitRatio: "2",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a split transaction with a zero ratio", () => {
    const result = addTransactionSchema.safeParse({
      type: "split",
      executedAt: "2026-01-01T00:00:00Z",
      instrumentId: "11111111-1111-1111-1111-111111111111",
      splitRatio: "0",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid deposit transaction with only cashAmount", () => {
    const result = addTransactionSchema.safeParse({
      type: "deposit",
      executedAt: "2026-01-01T00:00:00Z",
      cashAmount: "1000",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a deposit transaction missing cashAmount", () => {
    const result = addTransactionSchema.safeParse({
      type: "deposit",
      executedAt: "2026-01-01T00:00:00Z",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a valid transfer_out transaction with only quantity", () => {
    const result = addTransactionSchema.safeParse({
      type: "transfer_out",
      executedAt: "2026-01-01T00:00:00Z",
      instrumentId: "11111111-1111-1111-1111-111111111111",
      quantity: "5",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a missing executedAt", () => {
    const result = addTransactionSchema.safeParse({
      type: "deposit",
      cashAmount: "1000",
    });
    expect(result.success).toBe(false);
  });
});
