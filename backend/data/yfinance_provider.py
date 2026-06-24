"""yfinance implementation of ChainProvider.

This is the *only* module that knows yfinance's shape. yfinance is a free,
unofficial source: it rate-limits, changes shape, and returns empty/stale data
without warning (docs/architecture.md). So every failure mode is caught and
re-raised as one of our ``ChainError`` subclasses, and yfinance is imported
lazily so the rest of the backend neither imports nor depends on it at module
load.

The mapping itself (provider records -> our OptionChain) is factored into pure
module-level functions so it can be tested with synthetic records, without a
network call or even yfinance installed.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

from data.chain import ExpiryChain, OptionChain, OptionQuote
from data.provider import ChainFetchError, EmptyChainError

# Cap on how many expiries we pull: each is a separate network round-trip, and a
# handful is plenty for a pricing/analysis tool.
MAX_EXPIRIES = 6
_DAYS_PER_YEAR = 365.0


def _clean_float(value: Any) -> float | None:
    """Provider missing values arrive as None or NaN; normalize both to None."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _clean_int(value: Any) -> int | None:
    f = _clean_float(value)
    return None if f is None else int(f)


def record_to_quote(record: dict[str, Any], option_type: str) -> OptionQuote:
    """Map one yfinance row (as a dict) to a normalized OptionQuote."""
    return OptionQuote(
        contract_symbol=str(record.get("contractSymbol", "")),
        option_type=option_type,
        strike=float(record["strike"]),
        last_price=_clean_float(record.get("lastPrice")),
        bid=_clean_float(record.get("bid")),
        ask=_clean_float(record.get("ask")),
        volume=_clean_int(record.get("volume")),
        open_interest=_clean_int(record.get("openInterest")),
        implied_volatility=_clean_float(record.get("impliedVolatility")),
        in_the_money=(None if record.get("inTheMoney") is None
                      else bool(record.get("inTheMoney"))),
    )


def build_option_chain(
    ticker: str,
    spot: float,
    fetched_at: datetime,
    raw_expiries: list[tuple[date, list[dict[str, Any]], list[dict[str, Any]]]],
) -> OptionChain:
    """Assemble an OptionChain from provider records (pure, no I/O).

    Skips expiries already in the past (stale). Raises EmptyChainError if
    nothing usable remains.
    """
    fetched_date = fetched_at.date()
    expiries: list[ExpiryChain] = []
    for expiry, call_records, put_records in raw_expiries:
        days = (expiry - fetched_date).days
        if days < 0:
            continue  # expired / stale -- drop it
        expiries.append(ExpiryChain(
            expiry=expiry,
            time_to_expiry=days / _DAYS_PER_YEAR,
            calls=[record_to_quote(r, "call") for r in call_records],
            puts=[record_to_quote(r, "put") for r in put_records],
        ))
    if not expiries:
        raise EmptyChainError(f"no current option expiries returned for {ticker}")
    return OptionChain(ticker=ticker, spot=spot, fetched_at=fetched_at,
                       expiries=expiries)


class YFinanceProvider:
    """Fetches chains from yfinance and maps them to our OptionChain type."""

    def __init__(self, max_expiries: int = MAX_EXPIRIES) -> None:
        self.max_expiries = max_expiries

    def get_option_chain(self, ticker: str) -> OptionChain:
        try:
            import yfinance  # lazy: keeps the dependency off the import path
        except ImportError as exc:  # pragma: no cover - deploy-time config
            raise ChainFetchError("yfinance is not installed") from exc

        try:
            handle = yfinance.Ticker(ticker)
            spot = self._resolve_spot(handle)
            expiry_strings = list(handle.options or [])[: self.max_expiries]
            if not expiry_strings:
                raise EmptyChainError(f"no expiries listed for {ticker}")
            raw_expiries = []
            for expiry_string in expiry_strings:
                table = handle.option_chain(expiry_string)
                raw_expiries.append((
                    date.fromisoformat(expiry_string),
                    table.calls.to_dict("records"),
                    table.puts.to_dict("records"),
                ))
        except EmptyChainError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize any provider failure
            raise ChainFetchError(
                f"failed to fetch chain for {ticker}: {exc}") from exc

        return build_option_chain(
            ticker, spot, datetime.now(UTC), raw_expiries)

    @staticmethod
    def _resolve_spot(handle: Any) -> float:
        """Best-effort current price across the fields yfinance exposes."""
        fast_info = getattr(handle, "fast_info", None)
        if fast_info is not None:
            for key in ("last_price", "lastPrice", "last_close"):
                try:
                    value = fast_info[key]
                except (KeyError, TypeError):
                    value = getattr(fast_info, key, None)
                cleaned = _clean_float(value)
                if cleaned and cleaned > 0:
                    return cleaned
        raise ChainFetchError("could not resolve a spot price")
