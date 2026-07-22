"""MarketDataCache — Redis-backed quote caching using the redis-cache
instance (Document 3 §7.7's 3-way split).

Per Document 5 §13.1's cache-invalidation decision tree: quotes are
"high-write-frequency... no explicit invalidation, just overwrite on
every write (last-write-wins, acceptable because staleness window is
sub-second)." A short TTL (30s) is applied on top of that as a safety net
specific to this phase's implementation — Document 5's "sub-second
staleness" assumption presumes a continuously-running streaming/polling
ingestion pipeline (Document 5 §11.2) keeping the cache warm; this phase's
background sync (Celery beat, task 7) polls periodically rather than
streaming continuously, so an unbounded-TTL cache entry could otherwise
go stale for longer than acceptable if the periodic job stalls. The TTL
is a disclosed, narrower interim than the frozen architecture's assumption,
not a silent deviation.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from decimal import Decimal
from typing import cast

from redis.asyncio import Redis

from src.application.market_data.provider import QuoteResult
from src.domain.market_data.value_objects import Price

_QUOTE_KEY_PREFIX = "market_data:quote:"
_QUOTE_TTL_SECONDS = 30


def _quote_key(symbol: str) -> str:
    return f"{_QUOTE_KEY_PREFIX}{symbol.upper()}"


class MarketDataCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_quote(self, symbol: str) -> QuoteResult | None:
        # redis-py's type stubs resolve hgetall/hset/expire's return type
        # ambiguously between the sync and async client overloads (a
        # known stub gap — get/incr/delete/ttl, used elsewhere in this
        # codebase, resolve correctly; only the hash-map methods don't).
        # cast() documents precisely what's actually true at runtime
        # (this is the asyncio Redis client, always awaitable) rather than
        # a blanket per-line `# type: ignore` that would also hide a
        # genuine future error.
        raw = await cast(Awaitable[dict[str, str]], self._redis.hgetall(_quote_key(symbol)))
        if not raw:
            return None
        return QuoteResult(
            symbol=raw["symbol"],
            price=Price(Decimal(raw["price"])),
            previous_close=(
                Price(Decimal(raw["previous_close"])) if raw.get("previous_close") else None
            ),
            as_of=datetime.fromisoformat(raw["as_of"]),
            source=raw["source"],
        )

    async def set_quote(self, quote: QuoteResult) -> None:
        key = _quote_key(quote.symbol)
        mapping = {
            "symbol": quote.symbol,
            "price": str(quote.price.amount),
            "as_of": quote.as_of.isoformat(),
            "source": quote.source,
        }
        if quote.previous_close is not None:
            mapping["previous_close"] = str(quote.previous_close.amount)
        await cast(Awaitable[int], self._redis.hset(key, mapping=mapping))
        await cast(Awaitable[bool], self._redis.expire(key, _QUOTE_TTL_SECONDS))
