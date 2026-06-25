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

# Cap on how many expiries we pull: each is a separate network round-trip, so we
# bound the cold-cache fetch. We do NOT take the nearest N contiguous expiries --
# for an index like SPY that is ten weeklies all inside ~5 weeks, which gives the
# vol surface a thin, front-clustered term-structure axis. Instead we SAMPLE the
# curve: pick the listed expiry nearest each target tenor below, so the surface
# spans a near weekly through liquid monthlies/quarterlies out to ~1 year.
MAX_EXPIRIES = 10
_TARGET_TENOR_DAYS = (7, 30, 60, 90, 120, 180, 270, 365)
_DAYS_PER_YEAR = 365.0


def _select_expiries(
    expiry_strings: list[str], today: date, max_expiries: int,
) -> list[str]:
    """Sample expiries across the term structure rather than taking the nearest
    contiguous block. For each target tenor we keep the listed expiry with the
    closest day-count; results are de-duplicated and returned in date order.

    Pure (no network) so the sampling is unit-testable. Past/today expiries are
    skipped. Degenerate inputs (few or all-short-dated expiries) collapse onto
    whatever exists, so the caller still gets a valid, ordered subset.
    """
    dated: list[tuple[int, str]] = []
    for s in expiry_strings:
        try:
            days = (date.fromisoformat(s) - today).days
        except ValueError:
            continue
        if days >= 1:
            dated.append((days, s))
    if not dated:
        return []

    chosen: set[str] = set()
    for target in _TARGET_TENOR_DAYS:
        _, nearest = min(dated, key=lambda d: (abs(d[0] - target), d[0]))
        chosen.add(nearest)
        if len(chosen) >= max_expiries:
            break
    return [s for _, s in sorted(dated) if s in chosen]


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


def _clean_datetime(value: Any) -> datetime | None:
    """Normalize a provider timestamp (pandas Timestamp / NaT / str) to a
    timezone-aware UTC datetime, or None when it is missing or unparseable."""
    if value is None:
        return None
    # pandas NaT and float NaN are not equal to themselves.
    if value != value:  # noqa: PLR0124 - NaN/NaT sentinel check
        return None
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        try:
            value = to_pydatetime()
        except (ValueError, TypeError):
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


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
        last_trade_date=_clean_datetime(record.get("lastTradeDate")),
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

        # Setup (handle, spot, expiry listing). A failure here is total -- we
        # have no spot/forward and nothing to show -- so it surfaces as 502.
        try:
            handle = yfinance.Ticker(ticker)
            spot = self._resolve_spot(handle)
            today = datetime.now(UTC).date()
            expiry_strings = _select_expiries(
                list(handle.options or []), today, self.max_expiries)
        except Exception as exc:  # noqa: BLE001 - normalize any provider failure
            raise ChainFetchError(
                f"failed to fetch chain for {ticker}: {exc}") from exc
        if not expiry_strings:
            raise EmptyChainError(f"no expiries listed for {ticker}")

        # Per-expiry fetches are EACH a network round-trip, and yfinance commonly
        # rate-limits partway through. Tolerate per-expiry failures: keep every
        # expiry that succeeds and skip the ones that don't, so a partial fetch
        # still yields a (smaller) surface rather than discarding good slices.
        raw_expiries: list[
            tuple[date, list[dict[str, Any]], list[dict[str, Any]]]
        ] = []
        for expiry_string in expiry_strings:
            try:
                table = handle.option_chain(expiry_string)
                raw_expiries.append((
                    date.fromisoformat(expiry_string),
                    table.calls.to_dict("records"),
                    table.puts.to_dict("records"),
                ))
            except Exception:  # noqa: BLE001 - one bad expiry must not sink the rest
                continue

        # Only a *complete* failure (every expiry errored) is an error response.
        if not raw_expiries:
            raise ChainFetchError(
                f"failed to fetch any expiry for {ticker} (source unavailable "
                "or rate-limited)")

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
