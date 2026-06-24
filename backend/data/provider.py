"""The data-provider interface and its error vocabulary.

Downstream code depends on the ``ChainProvider`` protocol and these exceptions,
not on any concrete provider. The yfinance implementation lives in
``yfinance_provider`` and is the only module that knows the provider's shape.
"""

from __future__ import annotations

from typing import Protocol

from data.chain import OptionChain

# A small whitelist of liquid underlyings. Restricting the set keeps the tool
# focused, keeps payloads/latency sane, and avoids hammering a free data source
# with arbitrary symbols.
SUPPORTED_TICKERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "TSLA",
)


class ChainError(Exception):
    """Base class for data-layer failures."""


class UnsupportedTickerError(ChainError):
    """The requested ticker is not in the supported whitelist."""


class EmptyChainError(ChainError):
    """The provider returned no usable (non-expired) option data."""


class ChainFetchError(ChainError):
    """The provider call failed (network, rate limit, unexpected shape)."""


class ChainProvider(Protocol):
    """Anything that can return one of our normalized chains for a ticker."""

    def get_option_chain(self, ticker: str) -> OptionChain:
        ...
