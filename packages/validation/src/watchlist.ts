import { z } from "zod";

/**
 * Watchlist form schemas — must match the backend's Pydantic DTOs exactly
 * (apps/core-api/src/presentation/dto/watchlist_dto.py) so client-side
 * validation never accepts something the server will reject. Per
 * ADR-0004: watchlist names are capped at 100 chars (vs. Portfolio's 200),
 * matching Watchlist.MAX_NAME_LENGTH in the domain layer exactly.
 */

const WATCHLIST_NAME_MAX_LENGTH = 100;

export const createWatchlistSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Watchlist name is required")
    .max(WATCHLIST_NAME_MAX_LENGTH, "Name is too long"),
  isDefault: z.boolean().default(false),
});
export type CreateWatchlistFormValues = z.infer<typeof createWatchlistSchema>;

export const updateWatchlistSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Watchlist name is required")
    .max(WATCHLIST_NAME_MAX_LENGTH, "Name is too long"),
  isDefault: z.boolean().optional(),
});
export type UpdateWatchlistFormValues = z.infer<typeof updateWatchlistSchema>;

/**
 * Symbol format is intentionally permissive here (uppercased on submit,
 * final validation is server-side against the real instruments table via
 * SearchInstrumentsUseCase's symbol resolution) — this mirrors
 * StockSearch's existing pattern of letting the backend be the source of
 * truth for "does this symbol actually exist," not duplicating a static
 * symbol-format regex on the client that could drift from real listings.
 */
export const addWatchlistItemSchema = z.object({
  symbol: z
    .string()
    .trim()
    .min(1, "A symbol is required")
    .max(20, "Symbol is too long")
    .transform((val) => val.toUpperCase()),
});
export type AddWatchlistItemFormValues = z.infer<typeof addWatchlistItemSchema>;

export const updateWatchlistItemSchema = z.object({
  isPinned: z.boolean().optional(),
  position: z.number().int().min(0).optional(),
});
export type UpdateWatchlistItemFormValues = z.infer<typeof updateWatchlistItemSchema>;
