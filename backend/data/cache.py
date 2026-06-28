"""An in-memory TTL cache in front of a chain provider.

Fetching every expiry from a free source is several slow HTTP round-trips, and
the vol-surface and chain endpoints hit the same data. This wraps any
``ChainProvider`` and serves a recently-fetched chain for a ticker instead of
re-fetching within the TTL.

This is a read-through request cache, NOT persistence: it is process-local,
holds nothing across a restart, and adds no database or user state. It does not
violate the stateless design (docs/architecture.md) — it only avoids hammering
a rate-limited source.
"""

from __future__ import annotations

import threading
import time

from data.chain import OptionChain, PriceHistory
from data.provider import HISTORY_LOOKBACK_DAYS, ChainProvider

# How long a fetched chain is served before re-fetching. Chains move slowly
# relative to a page view; 10 minutes keeps data fresh while cutting load.
CACHE_TTL_SECONDS: float = 600.0


class CachingChainProvider:
    """Wraps a provider with per-ticker TTL caches for both the chain and the
    price history. Implements ChainProvider."""

    def __init__(self, inner: ChainProvider,
                 ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, OptionChain]] = {}
        self._history_cache: dict[tuple[str, int], tuple[float, PriceHistory]] = {}

    def get_option_chain(self, ticker: str) -> OptionChain:
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(ticker)
            if entry is not None and now - entry[0] < self._ttl:
                return entry[1]
        # Fetch outside the lock so a slow upstream call doesn't serialize every
        # request; failures propagate and are simply not cached.
        chain = self._inner.get_option_chain(ticker)
        with self._lock:
            self._cache[ticker] = (time.monotonic(), chain)
        return chain

    def get_price_history(
        self, ticker: str, lookback_days: int = HISTORY_LOOKBACK_DAYS,
    ) -> PriceHistory:
        key = (ticker, lookback_days)
        now = time.monotonic()
        with self._lock:
            entry = self._history_cache.get(key)
            if entry is not None and now - entry[0] < self._ttl:
                return entry[1]
        # Fetch outside the lock (see get_option_chain); failures are not cached.
        history = self._inner.get_price_history(ticker, lookback_days)
        with self._lock:
            self._history_cache[key] = (time.monotonic(), history)
        return history
