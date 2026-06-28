"""Options-chain data access, behind a single interface.

Downstream code depends on our own ``OptionChain`` type and the ``ChainProvider``
protocol, never on a provider's raw shape. One adapter module
(``yfinance_provider``) does the provider-specific fetching and maps to
``OptionChain``, so swapping the data source is a one-file change (see
docs/architecture.md).
"""

from __future__ import annotations

from functools import lru_cache

from data.cache import CachingChainProvider
from data.chain import (
    ExpiryChain,
    OptionChain,
    OptionQuote,
    PriceHistory,
    PricePoint,
)
from data.provider import (
    HISTORY_LOOKBACK_DAYS,
    RISK_FREE_RATE,
    SUPPORTED_TICKERS,
    ChainError,
    ChainFetchError,
    ChainProvider,
    EmptyChainError,
    UnsupportedTickerError,
    dividend_yield_for,
)
from data.yfinance_provider import YFinanceProvider

__all__ = [
    "OptionChain",
    "ExpiryChain",
    "OptionQuote",
    "PriceHistory",
    "PricePoint",
    "ChainProvider",
    "ChainError",
    "ChainFetchError",
    "EmptyChainError",
    "UnsupportedTickerError",
    "SUPPORTED_TICKERS",
    "RISK_FREE_RATE",
    "HISTORY_LOOKBACK_DAYS",
    "dividend_yield_for",
    "get_option_chain",
    "get_price_history",
    "get_chain_provider",
]


@lru_cache(maxsize=1)
def get_chain_provider() -> ChainProvider:
    """The default provider. A FastAPI dependency so tests can override it with
    a fake (no network). Cached so the provider is built once. Wrapped in a TTL
    cache so the chain and vol-surface endpoints don't re-hit the source."""
    return CachingChainProvider(YFinanceProvider())


def get_option_chain(ticker: str, provider: ChainProvider | None = None) -> OptionChain:
    """Fetch a normalized chain for a supported ticker.

    Validates the ticker against the whitelist, then delegates to the provider.
    Raises UnsupportedTickerError for anything off the whitelist; other failures
    surface as the provider's ChainError subclasses.
    """
    symbol = _validate_ticker(ticker)
    active_provider = provider or get_chain_provider()
    return active_provider.get_option_chain(symbol)


def get_price_history(
    ticker: str,
    lookback_days: int = HISTORY_LOOKBACK_DAYS,
    provider: ChainProvider | None = None,
) -> PriceHistory:
    """Fetch a normalized daily price history for a supported ticker.

    Same whitelist discipline as get_option_chain: rejects off-whitelist symbols
    before touching the provider; other failures surface as ChainError subclasses.
    """
    symbol = _validate_ticker(ticker)
    active_provider = provider or get_chain_provider()
    return active_provider.get_price_history(symbol, lookback_days)


def _validate_ticker(ticker: str) -> str:
    """Normalize and whitelist-check a ticker, or raise UnsupportedTickerError."""
    symbol = ticker.strip().upper()
    if symbol not in SUPPORTED_TICKERS:
        raise UnsupportedTickerError(
            f"{symbol!r} is not supported; choose one of "
            f"{', '.join(SUPPORTED_TICKERS)}")
    return symbol
