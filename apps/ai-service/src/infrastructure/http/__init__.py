"""HTTP-based repository implementations calling core-api's existing
public REST endpoints — per the founder's Phase 7 instruction: "Reuse the
existing Market Data module... Never duplicate data." ai-service never
opens its own Postgres connection or duplicates the ohlcv_bars table.
"""
