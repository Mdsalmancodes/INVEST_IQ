import { describe, expect, it } from "vitest";

import { createAlertSchema, updateAlertSchema } from "./alerts";

describe("createAlertSchema", () => {
  it("accepts a valid alert and uppercases the symbol", () => {
    const result = createAlertSchema.safeParse({
      symbol: "aapl",
      conditionType: "price_above",
      threshold: "150.50",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.symbol).toBe("AAPL");
      expect(result.data.isRecurring).toBe(false);
      expect(result.data.cooldownMinutes).toBe(0);
    }
  });

  it("accepts all valid condition types", () => {
    for (const conditionType of ["price_above", "price_below", "pct_change", "rsi_threshold"]) {
      const result = createAlertSchema.safeParse({
        symbol: "AAPL",
        conditionType,
        threshold: "10",
      });
      expect(result.success).toBe(true);
    }
  });

  it("rejects an invalid condition type", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "volume_spike",
      threshold: "10",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an empty symbol", () => {
    const result = createAlertSchema.safeParse({
      symbol: "",
      conditionType: "price_above",
      threshold: "10",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a non-numeric threshold", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "price_above",
      threshold: "not-a-number",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an empty threshold", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "price_above",
      threshold: "",
    });
    expect(result.success).toBe(false);
  });

  it("accepts a decimal threshold", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "pct_change",
      threshold: "5.25",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a negative cooldown", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "price_above",
      threshold: "10",
      cooldownMinutes: -5,
    });
    expect(result.success).toBe(false);
  });

  it("accepts isRecurring and cooldownMinutes together", () => {
    const result = createAlertSchema.safeParse({
      symbol: "AAPL",
      conditionType: "price_above",
      threshold: "10",
      isRecurring: true,
      cooldownMinutes: 60,
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.isRecurring).toBe(true);
      expect(result.data.cooldownMinutes).toBe(60);
    }
  });
});

describe("updateAlertSchema", () => {
  it("accepts an empty object (all fields optional)", () => {
    expect(updateAlertSchema.safeParse({}).success).toBe(true);
  });

  it("accepts threshold alone", () => {
    expect(updateAlertSchema.safeParse({ threshold: "200" }).success).toBe(true);
  });

  it("accepts isActive alone", () => {
    expect(updateAlertSchema.safeParse({ isActive: false }).success).toBe(true);
  });

  it("rejects an invalid threshold format", () => {
    expect(updateAlertSchema.safeParse({ threshold: "abc" }).success).toBe(false);
  });

  it("rejects a negative cooldown", () => {
    expect(updateAlertSchema.safeParse({ cooldownMinutes: -1 }).success).toBe(false);
  });
});
