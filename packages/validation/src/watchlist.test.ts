import { describe, expect, it } from "vitest";

import {
  addWatchlistItemSchema,
  createWatchlistSchema,
  updateWatchlistItemSchema,
  updateWatchlistSchema,
} from "./watchlist";

describe("createWatchlistSchema", () => {
  it("accepts a valid name", () => {
    const result = createWatchlistSchema.safeParse({ name: "Tech Stocks" });
    expect(result.success).toBe(true);
  });

  it("trims whitespace from the name", () => {
    const result = createWatchlistSchema.safeParse({ name: "  Tech Stocks  " });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.name).toBe("Tech Stocks");
    }
  });

  it("defaults isDefault to false when omitted", () => {
    const result = createWatchlistSchema.safeParse({ name: "Watchlist" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.isDefault).toBe(false);
    }
  });

  it("rejects an empty name", () => {
    expect(createWatchlistSchema.safeParse({ name: "" }).success).toBe(false);
  });

  it("rejects a name over 100 characters", () => {
    expect(createWatchlistSchema.safeParse({ name: "x".repeat(101) }).success).toBe(false);
  });

  it("accepts a name at exactly 100 characters", () => {
    expect(createWatchlistSchema.safeParse({ name: "x".repeat(100) }).success).toBe(true);
  });
});

describe("updateWatchlistSchema", () => {
  it("accepts a valid rename", () => {
    expect(updateWatchlistSchema.safeParse({ name: "New Name" }).success).toBe(true);
  });

  it("accepts isDefault without a name change conflict (name is still required)", () => {
    const result = updateWatchlistSchema.safeParse({ name: "Watchlist", isDefault: true });
    expect(result.success).toBe(true);
  });

  it("rejects an empty name", () => {
    expect(updateWatchlistSchema.safeParse({ name: "" }).success).toBe(false);
  });
});

describe("addWatchlistItemSchema", () => {
  it("accepts a valid symbol and uppercases it", () => {
    const result = addWatchlistItemSchema.safeParse({ symbol: "aapl" });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.symbol).toBe("AAPL");
    }
  });

  it("trims whitespace before uppercasing", () => {
    const result = addWatchlistItemSchema.safeParse({ symbol: "  msft  " });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.symbol).toBe("MSFT");
    }
  });

  it("rejects an empty symbol", () => {
    expect(addWatchlistItemSchema.safeParse({ symbol: "" }).success).toBe(false);
  });

  it("rejects a symbol over 20 characters", () => {
    expect(addWatchlistItemSchema.safeParse({ symbol: "x".repeat(21) }).success).toBe(false);
  });
});

describe("updateWatchlistItemSchema", () => {
  it("accepts isPinned alone", () => {
    expect(updateWatchlistItemSchema.safeParse({ isPinned: true }).success).toBe(true);
  });

  it("accepts position alone", () => {
    expect(updateWatchlistItemSchema.safeParse({ position: 2 }).success).toBe(true);
  });

  it("accepts both fields together", () => {
    const result = updateWatchlistItemSchema.safeParse({ isPinned: false, position: 0 });
    expect(result.success).toBe(true);
  });

  it("accepts an empty object (both optional)", () => {
    expect(updateWatchlistItemSchema.safeParse({}).success).toBe(true);
  });

  it("rejects a negative position", () => {
    expect(updateWatchlistItemSchema.safeParse({ position: -1 }).success).toBe(false);
  });

  it("rejects a non-integer position", () => {
    expect(updateWatchlistItemSchema.safeParse({ position: 1.5 }).success).toBe(false);
  });
});
