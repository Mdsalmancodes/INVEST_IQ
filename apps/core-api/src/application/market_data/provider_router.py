"""ProviderRouter — Document 5 §11.1's failover-capable provider selection.

Per the founder's explicit Phase 4 scope: simple ordered failover (try
providers in a configured priority order, fall through to the next on
failure), NOT the frozen architecture's full FeatureEntitlement-based
tier routing (`ProviderRouter.resolve(user, requirement)`) — no
FeatureEntitlement system exists anywhere in this codebase yet; that's a
genuinely later-phase concept (Document 5 §11.1 itself frames it as what
unlocks tiered real-time access for Pro users, which requires a
subscription/entitlement system this phase doesn't build). This is a
disclosed simplification with a clear upgrade path: ProviderRouter's
public methods (resolve_quote/resolve_bars) can later take a `user`
parameter and consult FeatureEntitlement without changing any caller.
"""

from __future__ import annotations

from datetime import date

from observability import get_logger

from src.application.market_data.provider import (
    BarResult,
    HistoricalDataProvider,
    QuoteResult,
    RealtimeQuoteProvider,
)
from src.domain.market_data.exceptions import AllProvidersFailedError
from src.domain.market_data.value_objects import Interval

logger = get_logger(__name__)


class ProviderRouter:
    """Tries each configured provider in order; falls through to the next
    on any exception, raising AllProvidersFailedError only if every
    provider in the chain fails. The ordering itself IS the "priority" —
    callers construct this with providers listed from most-preferred
    (e.g. a paid real-time source) to least-preferred (e.g. yfinance,
    dev-only, listed last so it only serves as an absolute fallback if
    even the intended primary providers are unavailable — production
    deployments should not include it in the chain at all, since Document
    5 §11.1 explicitly marks it "never used in production").
    """

    def __init__(
        self,
        quote_providers: tuple[RealtimeQuoteProvider, ...],
        historical_providers: tuple[HistoricalDataProvider, ...],
    ) -> None:
        if not quote_providers:
            raise ValueError("ProviderRouter requires at least one quote provider")
        if not historical_providers:
            raise ValueError("ProviderRouter requires at least one historical provider")
        self._quote_providers = quote_providers
        self._historical_providers = historical_providers

    async def resolve_quote(self, symbol: str) -> QuoteResult:
        errors: list[str] = []
        for provider in self._quote_providers:
            try:
                return await provider.get_quote(symbol)
            except Exception as exc:  # noqa: BLE001 - deliberately broad: any
                # vendor-specific exception must not leak past this boundary
                # (Document 5 §11.1's entire point), we only need to know it
                # failed and try the next provider.
                logger.warning(
                    "market_data.provider.quote_failed",
                    provider=getattr(provider, "name", provider.__class__.__name__),
                    symbol=symbol,
                    error=str(exc),
                )
                errors.append(f"{provider.__class__.__name__}: {exc}")
        raise AllProvidersFailedError(
            f"All quote providers failed for symbol {symbol!r}: {'; '.join(errors)}"
        )

    async def resolve_bars(
        self, symbol: str, interval: Interval, start: date, end: date
    ) -> tuple[BarResult, ...]:
        errors: list[str] = []
        for provider in self._historical_providers:
            try:
                return await provider.get_bars(symbol, interval, start, end)
            except Exception as exc:  # noqa: BLE001 - see resolve_quote's rationale
                logger.warning(
                    "market_data.provider.bars_failed",
                    provider=getattr(provider, "name", provider.__class__.__name__),
                    symbol=symbol,
                    interval=interval.value,
                    error=str(exc),
                )
                errors.append(f"{provider.__class__.__name__}: {exc}")
        raise AllProvidersFailedError(
            f"All historical providers failed for symbol {symbol!r}: {'; '.join(errors)}"
        )
