"""Compare a ticker's forward-looking implied volatility against its
backward-looking realized volatility.

Pure: a normalized ``OptionChain`` and a ``PriceHistory`` go in, a
``VolComparison`` comes out. No network, no file I/O, no FastAPI imports
(docs/architecture.md) -- the route fetches the chain and the price history, this
module only does the modeling.

The honest construction (the crux -- get this wrong and the feature misleads):

  - **Realized vol is a backward-looking time series.** A rolling close-to-close
    estimate over the trailing window (``pricing.realized_vol``); each point
    reflects what the underlying actually did over the *preceding* ~month.

  - **Implied vol is a single forward-looking observation.** We only ever see
    *today's* chain -- a free data source gives no history of option quotes, and
    v1 is stateless (no stored IV snapshots) -- so there is no historical implied
    series to plot. We surface today's ATM-forward implied vol for the near-dated
    expiry as one forward point, NOT a fabricated line drawn back across history.

  - **The premium is a same-date spread**, today's implied minus the most recent
    realized vol, with the realized window length (21 trading days ~ one calendar
    month) chosen to match the ~30-calendar-day implied horizon. It is explicitly
    NOT a forecast-vs-outcome backtest: see ``VOL_PREMIUM_NOTE``.

  - **ATM-forward implied vol** is interpolated to forward log-moneyness k = 0
    using OUR solver's IVs (via ``pricing.vol_surface``), never the provider's
    own implied-volatility field -- the backend owns all numerics, same
    discipline as the surface. The near-dated expiry is the one whose
    time-to-expiry is closest to 30 days; we report its actual day count.

Units follow ``pricing.black_scholes``: rates/vols are decimals, time is years.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from data.chain import OptionChain, PriceHistory
from pricing.realized_vol import (
    DEFAULT_WINDOW_TRADING_DAYS,
    TRADING_DAYS_PER_YEAR,
    rolling_realized_vol,
)
from pricing.vol_surface import ExpirySlice, build_vol_surface

# The near-dated expiry we read implied vol from: the listed expiry whose
# time-to-expiry is closest to this many days. Its *actual* day count is
# reported, so a 27d or 34d expiry is labelled honestly rather than as "30d".
IMPLIED_TARGET_DAYS = 30
_DAYS_PER_YEAR = 365.0

# The framing that must travel with the premium everywhere it is shown (chart
# included, not just the README). Defined once here so the wording cannot drift.
VOL_PREMIUM_NOTE = (
    "Implied vol minus recent realized vol — the market's current "
    "expectation relative to recent history, not a forecast or signal."
)


@dataclass(frozen=True)
class RealizedVolPoint:
    """One date's annualized realized vol (decimal)."""

    date: date
    realized_vol: float


@dataclass(frozen=True)
class VolComparison:
    """Implied-vs-realized comparison for one ticker, with its assumptions.

    The asymmetry is intentional and honest: ``realized`` is a full backward
    series; the implied fields are a single forward observation (today's chain).
    ``vol_premium`` is the same-date spread, defined only when both exist.
    """

    ticker: str
    spot: float
    fetched_at: datetime
    risk_free_rate: float
    dividend_yield: float

    # Backward-looking series.
    realized_window_trading_days: int
    trading_days_per_year: int
    realized: tuple[RealizedVolPoint, ...]
    latest_realized_vol: float | None  # most recent realized point, for the spread

    # Forward-looking single observation (today's near-dated ATM-forward IV).
    implied_atm_vol: float | None
    implied_expiry: date | None
    implied_days_to_expiry: int | None
    implied_time_to_expiry: float | None
    forward: float | None
    atm_method: str | None  # "interpolated" or "nearest-strike"

    # Same-date spread and its mandatory framing.
    vol_premium: float | None  # implied_atm_vol - latest_realized_vol
    vol_premium_note: str


def _interpolate_atm_iv(slice_: ExpirySlice) -> tuple[float, str]:
    """ATM-forward implied vol for one expiry slice.

    The slice's points are sorted by forward log-moneyness k = ln(K/F). When the
    retained points bracket k = 0 we linearly interpolate the IV in k to the
    forward; otherwise (only one wing survived the filters) we take the IV of the
    point nearest the forward and flag it as a nearest-strike read.

    Caller guarantees the slice has at least one point.
    """
    points = slice_.points  # already sorted ascending by log_moneyness
    below = [p for p in points if p.log_moneyness <= 0.0]
    above = [p for p in points if p.log_moneyness > 0.0]
    if below and above:
        lo, hi = below[-1], above[0]
        span = hi.log_moneyness - lo.log_moneyness
        # span > 0 here (lo.k <= 0 < hi.k); weight to k = 0.
        weight = (0.0 - lo.log_moneyness) / span
        iv = lo.implied_volatility + weight * (
            hi.implied_volatility - lo.implied_volatility)
        return iv, "interpolated"
    nearest = min(points, key=lambda p: abs(p.log_moneyness))
    return nearest.implied_volatility, "nearest-strike"


def build_vol_comparison(
    chain: OptionChain,
    price_history: PriceHistory,
    risk_free_rate: float,
    dividend_yield: float,
    *,
    realized_window: int = DEFAULT_WINDOW_TRADING_DAYS,
    target_days: int = IMPLIED_TARGET_DAYS,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> VolComparison:
    """Assemble the implied-vs-realized comparison (pure, no I/O).

    Args:
        chain: today's normalized option chain (for the forward implied read).
        price_history: daily closes for the realized series (chronological).
        risk_free_rate: r, annual continuously-compounded, decimal.
        dividend_yield: q, continuous dividend yield, decimal.
        realized_window: trailing trading-day window for realized vol (default 21
            ~ one calendar month, matching the ~30-day implied horizon).
        target_days: the implied read uses the expiry nearest this many days.
        trading_days: annualization factor's argument (default 252).

    Returns:
        A VolComparison. ``realized`` is the backward series (None-padded warm-up
        dropped); the implied fields are today's single forward observation, or
        all None if no expiry yielded a usable ATM read; ``vol_premium`` is the
        same-date spread, set only when both sides exist.
    """
    ordered = sorted(price_history.points, key=lambda p: p.date)
    closes = [p.close for p in ordered]
    series = rolling_realized_vol(closes, window=realized_window,
                                  trading_days=trading_days)
    realized = tuple(
        RealizedVolPoint(date=pt.date, realized_vol=vol)
        for pt, vol in zip(ordered, series, strict=True)
        if vol is not None
    )
    latest_realized = realized[-1].realized_vol if realized else None

    # Forward implied read: build the surface (our solver) and pick the slice
    # with points whose tenor is closest to the target, then interpolate to ATM.
    surface = build_vol_surface(chain, risk_free_rate, dividend_yield)
    candidate_slices = [s for s in surface.slices if s.points]
    implied_vol: float | None = None
    implied_expiry: date | None = None
    implied_dte: int | None = None
    implied_tte: float | None = None
    forward: float | None = None
    atm_method: str | None = None
    if candidate_slices:
        target_t = target_days / _DAYS_PER_YEAR
        atm_slice = min(candidate_slices,
                        key=lambda s: abs(s.time_to_expiry - target_t))
        implied_vol, atm_method = _interpolate_atm_iv(atm_slice)
        implied_expiry = atm_slice.expiry
        implied_tte = atm_slice.time_to_expiry
        implied_dte = round(atm_slice.time_to_expiry * _DAYS_PER_YEAR)
        forward = atm_slice.forward

    vol_premium = (
        implied_vol - latest_realized
        if implied_vol is not None and latest_realized is not None
        else None
    )

    return VolComparison(
        ticker=chain.ticker,
        spot=chain.spot,
        fetched_at=chain.fetched_at,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        realized_window_trading_days=realized_window,
        trading_days_per_year=trading_days,
        realized=realized,
        latest_realized_vol=latest_realized,
        implied_atm_vol=implied_vol,
        implied_expiry=implied_expiry,
        implied_days_to_expiry=implied_dte,
        implied_time_to_expiry=implied_tte,
        forward=forward,
        atm_method=atm_method,
        vol_premium=vol_premium,
        vol_premium_note=VOL_PREMIUM_NOTE,
    )
