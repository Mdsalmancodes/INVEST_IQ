"""Redis Pub/Sub channel naming scheme for Phase 9's real-time layer.

Centralized here so every publisher (market data streaming, portfolio
recalculation, AI prediction refresh, sentiment refresh, alert
evaluation) and the single WebSocket dispatch loop (realtime_service.py)
agree on exact channel names without duplicating string literals across
files — the same principle as Document 3's DTO-per-endpoint convention,
applied to channel names instead of response shapes.

Per-user channels are suffixed with the user's id so RealtimeService's
Redis listener can route a message to exactly that user's
ConnectionManager entry without needing to parse message content first.
Market-wide channels (ticker/index) have no per-user suffix — every
connected client receives them via ConnectionManager.broadcast().
"""

from __future__ import annotations

TICKER_CHANNEL = "realtime:ticker"
"""Market-wide index/ticker values — broadcast to every connected client."""


def quote_channel(symbol: str) -> str:
    """Per-symbol live quote updates (price/OHLC/volume/change/%change).
    Not per-user — any client watching this symbol (via watchlist or an
    open instrument-detail page) subscribes to the same channel; the WS
    router (task 3) tracks which symbols each connection is interested in
    and only forwards messages for those."""
    return f"realtime:quote:{symbol.upper()}"


def watchlist_channel(user_id: str) -> str:
    return f"realtime:watchlist:{user_id}"


def portfolio_channel(user_id: str, portfolio_id: str) -> str:
    return f"realtime:portfolio:{user_id}:{portfolio_id}"


def ai_prediction_channel(symbol: str) -> str:
    """Not per-user — a Buy/Sell/Hold recommendation for a symbol is the
    same for every user who happens to be watching it; there is no
    per-user personalization in the Decision Engine's output today
    (Phase 7), so this mirrors quote_channel's shape exactly."""
    return f"realtime:ai:{symbol.upper()}"


def sentiment_channel(symbol: str) -> str:
    return f"realtime:sentiment:{symbol.upper()}"


def alert_channel(user_id: str) -> str:
    return f"realtime:alert:{user_id}"
