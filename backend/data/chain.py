"""Our own options-chain domain types.

Everything downstream (API, frontend) depends on these, never on a data
provider's raw shape (docs/architecture.md). A provider adapter maps the
provider's response into these types; swapping providers is then a one-file
change.

These are pydantic models so the API can serialize a chain directly without a
second, parallel set of response types.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class OptionQuote(BaseModel):
    """A single listed contract's market data, normalized.

    Provider fields are often missing (illiquid strikes); those map to None
    rather than to a misleading zero or NaN.
    """

    contract_symbol: str
    option_type: str  # "call" or "put"
    strike: float
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None  # provider's IV, decimal
    in_the_money: bool | None = None
    # When this contract last printed a trade. Used as a staleness backstop in
    # the vol-surface builder (a tight two-sided quote with real OI is already
    # evidence of a live market). None when the provider omits it.
    last_trade_date: datetime | None = None


class ExpiryChain(BaseModel):
    """All calls and puts for one expiration date."""

    expiry: date
    time_to_expiry: float  # years from fetched_at, ACT/365
    calls: list[OptionQuote]
    puts: list[OptionQuote]


class OptionChain(BaseModel):
    """A ticker's chain across the returned expiries, with a fetch timestamp so
    clients can judge staleness (the data is from a free, best-effort source)."""

    ticker: str
    spot: float
    fetched_at: datetime
    expiries: list[ExpiryChain]


class PricePoint(BaseModel):
    """One trading day's closing price."""

    date: date
    close: float


class PriceHistory(BaseModel):
    """A ticker's daily closing prices over a lookback window, chronological.

    The realized-volatility series (V2-B) is computed from these closes. Like the
    chain, it carries a fetch timestamp because the source is free and delayed.
    """

    ticker: str
    fetched_at: datetime
    points: list[PricePoint]
