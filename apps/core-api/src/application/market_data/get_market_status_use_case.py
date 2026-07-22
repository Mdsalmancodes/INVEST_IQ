"""GetMarketStatusUseCase — NEW addition per the founder's explicit Phase 4
"Market Status API" requirement (no such endpoint exists in the frozen
Document 4 catalog; consistent with how Portfolio's /summary endpoint was
added in Phase 3 for a founder-requested capability the frozen catalog
didn't yet have).

Computes US equity market session status (NYSE/NASDAQ hours, the only
market this phase's instrument universe covers — Document 3 §8.1's
`instruments.exchange` values used elsewhere in this codebase are all
NASDAQ) using standard trading hours. Does NOT account for market
holidays (a real holiday calendar is a disclosed simplification, not
built this phase — the founder's requirement was "Market Status API" as
a capability, not a fully holiday-aware implementation, and this is
lower-risk to defer than the calculation/provider logic).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

_MARKET_TIMEZONE = ZoneInfo("America/New_York")
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)


@dataclass(frozen=True, slots=True)
class MarketStatusResult:
    is_open: bool
    session: str  # "open" | "closed" | "pre-market" | "after-hours"
    as_of: datetime
    next_open: datetime | None


class GetMarketStatusUseCase:
    def execute(self) -> MarketStatusResult:
        now_utc = datetime.now(UTC)
        now_market_tz = now_utc.astimezone(_MARKET_TIMEZONE)
        current_time = now_market_tz.time()
        is_weekday = now_market_tz.weekday() < 5  # Mon-Fri

        if is_weekday and _MARKET_OPEN <= current_time < _MARKET_CLOSE:
            return MarketStatusResult(is_open=True, session="open", as_of=now_utc, next_open=None)

        session = "closed"
        if is_weekday and current_time < _MARKET_OPEN:
            session = "pre-market"
        elif is_weekday and current_time >= _MARKET_CLOSE:
            session = "after-hours"

        next_open = self._compute_next_open(now_market_tz)
        return MarketStatusResult(
            is_open=False, session=session, as_of=now_utc, next_open=next_open
        )

    def _compute_next_open(self, now_market_tz: datetime) -> datetime:
        # Start from today's market-open time in market-local time, then
        # advance forward (at least one day if today's open has already
        # passed) until we land on a weekday.
        candidate = now_market_tz.replace(
            hour=_MARKET_OPEN.hour, minute=_MARKET_OPEN.minute, second=0, microsecond=0
        )
        if now_market_tz.time() >= _MARKET_OPEN:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:  # skip weekends (no holiday calendar - disclosed above)
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC)
