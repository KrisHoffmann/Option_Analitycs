"""The data-provider interface and its error vocabulary.

Downstream code depends on the ``ChainProvider`` protocol and these exceptions,
not on any concrete provider. The yfinance implementation lives in
``yfinance_provider`` and is the only module that knows the provider's shape.
"""

from __future__ import annotations

from typing import Protocol

from data.chain import OptionChain, PriceHistory

# A small whitelist of liquid underlyings. Restricting the set keeps the tool
# focused, keeps payloads/latency sane, and avoids hammering a free data source
# with arbitrary symbols.
SUPPORTED_TICKERS: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "SPY", "QQQ", "TSLA",
)

# Market assumptions for IV work (the vol surface). These are documented
# constants, not a live feed -- finance-standards.md blesses a hardcoded rate
# "just say so". Refresh manually.
#
# r: ~3-month US T-bill yield, mid-2026. IV is weakly sensitive to r for the
#    short-dated OTM options the surface is built from, so one constant suffices.
RISK_FREE_RATE: float = 0.043

# Lookback for the realized-volatility history (V2-B). ~12 months of calendar
# days yields ~252 trading closes -- enough for a full year of a rolling 21-day
# realized series with complete coverage.
HISTORY_LOOKBACK_DAYS: int = 365

# q per ticker: approximate trailing continuous dividend yields (a continuous
# approximation of discrete quarterly dividends). 0.0 for non-payers.
_DIVIDEND_YIELDS: dict[str, float] = {
    "AAPL": 0.004,
    "MSFT": 0.007,
    "NVDA": 0.0003,
    "AMZN": 0.0,
    "SPY": 0.012,
    "QQQ": 0.006,
    "TSLA": 0.0,
}


def dividend_yield_for(ticker: str) -> float:
    """Assumed continuous dividend yield q (decimal) for a supported ticker;
    0.0 for anything not in the table."""
    return _DIVIDEND_YIELDS.get(ticker.strip().upper(), 0.0)


class ChainError(Exception):
    """Base class for data-layer failures."""


class UnsupportedTickerError(ChainError):
    """The requested ticker is not in the supported whitelist."""


class EmptyChainError(ChainError):
    """The provider returned no usable (non-expired) option data."""


class ChainFetchError(ChainError):
    """The provider call failed (network, rate limit, unexpected shape)."""


class ChainProvider(Protocol):
    """Our single data boundary: anything that can return a normalized option
    chain and a daily price history for a ticker."""

    def get_option_chain(self, ticker: str) -> OptionChain:
        ...

    def get_price_history(
        self, ticker: str, lookback_days: int = HISTORY_LOOKBACK_DAYS,
    ) -> PriceHistory:
        ...
