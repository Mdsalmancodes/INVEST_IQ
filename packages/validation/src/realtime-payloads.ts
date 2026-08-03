import { z } from "zod";

/**
 * Runtime validation schemas for WebSocket payloads pushed by
 * apps/core-api's realtime streaming services (Phase 9). Unlike the
 * form-input schemas elsewhere in this package, these validate data
 * received FROM the server over an untrusted transport (a WS message
 * whose shape a malicious or misbehaving upstream/proxy could tamper
 * with, unlike a same-origin fetch() response) — every consumer that
 * previously did `envelope.data as {...}` with zero runtime validation
 * (WatchlistTable, LiveQuote, NotificationsList) now parses through one
 * of these instead, matching this package's existing shared-Zod-schema
 * convention rather than each component inlining its own trust-the-cast
 * type assertion.
 */

/** MarketDataStreamingService's `quote:{symbol}` topic payload — see
 * apps/core-api/src/infrastructure/realtime/market_data_streaming_service.py's
 * _tick_to_payload. */
export const quoteTickSchema = z.object({
  symbol: z.string(),
  price: z.string(),
  previous_close: z.string().nullable(),
  is_stale_fallback: z.boolean(),
});
export type QuoteTick = z.infer<typeof quoteTickSchema>;

/** WatchlistStreamingService's `watchlist` topic payload — see
 * apps/core-api/src/infrastructure/realtime/watchlist_streaming_service.py's
 * _enriched_watchlist_to_payload. */
export const watchlistTickItemSchema = z.object({
  item_id: z.string(),
  price: z.string().nullable(),
  previous_close: z.string().nullable(),
  daily_change: z.string().nullable(),
  daily_change_pct: z.string().nullable(),
  is_delayed: z.boolean(),
  error: z.string().nullable(),
});
export const watchlistTickSchema = z.object({
  watchlist_id: z.string(),
  market_status: z.string().nullable(),
  items: z.array(watchlistTickItemSchema),
});
export type WatchlistTick = z.infer<typeof watchlistTickSchema>;

/** AlertEvaluationStreamingService's `alert` topic payload — the
 * triggered-alert push notification's title/body. */
export const alertNotificationTickSchema = z.object({
  title: z.string(),
  body: z.string(),
});
export type AlertNotificationTick = z.infer<typeof alertNotificationTickSchema>;
