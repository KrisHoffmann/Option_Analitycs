"""Options-chain data access, behind a single interface.

Downstream code depends on our own ``OptionChain`` type and the ``ChainProvider``
protocol, never on a provider's raw shape. One adapter module
(``yfinance_provider``) does the provider-specific fetching and maps to
``OptionChain``, so swapping the data source is a one-file change (see
docs/architecture.md).
"""

from __future__ import annotations

from functools import lru_cache

from data.chain import ExpiryChain, OptionChain, OptionQuote
from data.provider import (
    SUPPORTED_TICKERS,
    ChainError,
    ChainFetchError,
    ChainProvider,
    EmptyChainError,
    UnsupportedTickerError,
)
from data.yfinance_provider import YFinanceProvider

__all__ = [
    "OptionChain",
    "ExpiryChain",
    "OptionQuote",
    "ChainProvider",
    "ChainError",
    "ChainFetchError",
    "EmptyChainError",
    "UnsupportedTickerError",
    "SUPPORTED_TICKERS",
    "get_option_chain",
    "get_chain_provider",
]


@lru_cache(maxsize=1)
def get_chain_provider() -> ChainProvider:
    """The default provider. A FastAPI dependency so tests can override it with
    a fake (no network). Cached so the provider is built once."""
    return YFinanceProvider()


def get_option_chain(ticker: str, provider: ChainProvider | None = None) -> OptionChain:
    """Fetch a normalized chain for a supported ticker.

    Validates the ticker against the whitelist, then delegates to the provider.
    Raises UnsupportedTickerError for anything off the whitelist; other failures
    surface as the provider's ChainError subclasses.
    """
    symbol = ticker.strip().upper()
    if symbol not in SUPPORTED_TICKERS:
        raise UnsupportedTickerError(
            f"{symbol!r} is not supported; choose one of "
            f"{', '.join(SUPPORTED_TICKERS)}")
    active_provider = provider or get_chain_provider()
    return active_provider.get_option_chain(symbol)
