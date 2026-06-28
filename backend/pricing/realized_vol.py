"""Realized (historical) volatility from a daily close price series.

Pure scalar/series math: a sequence of closes goes in, an annualized rolling
realized-volatility series comes out. No I/O, no network, no globals, no FastAPI
imports (docs/architecture.md) -- the route layer fetches the prices, this module
only does the statistics.

Method (stated here and in the README, per docs/finance-standards.md):

  - **Close-to-close log returns.** r_t = ln(P_t / P_{t-1}). This is the textbook
    default and needs only closing prices. High-low estimators (Parkinson,
    Garman-Klass) are lower-variance alternatives that also use the intraday
    range; they are consciously NOT used here, for simplicity and because we only
    carry closes through the data layer.

  - **Rolling sample standard deviation**, mean-subtracted, ddof = 1 (an unbiased
    estimator of the return variance). The window is a fixed number of *trading
    days* (21 by default ~ one calendar month, matching the ~30-calendar-day
    horizon of the near-dated implied vol it is compared against).

  - **Annualization by sqrt(trading days per year) = sqrt(252)**, NOT sqrt(365).
    Daily-return volatility scales by the square root of the number of *trading*
    days in a year; using 365 is a common silent error that overstates vol.

This is backward-looking by construction: the realized vol at a date reflects
what the underlying actually did over the *preceding* window. That is the whole
point of comparing it against the forward-looking implied vol (see
``pricing.vol_comparison``).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

# One calendar month of trading sessions; the default rolling window. Kept as a
# named constant so the implied/realized horizon match is tunable in one place.
DEFAULT_WINDOW_TRADING_DAYS = 21

# Trading sessions per year -- the annualization factor is its square root.
# Deliberately 252 (trading days), never 365 (calendar days).
TRADING_DAYS_PER_YEAR = 252


def log_returns(closes: Sequence[float]) -> list[float]:
    """Close-to-close log returns r_t = ln(P_t / P_{t-1}).

    Args:
        closes: daily closing prices in chronological order, all > 0.

    Returns:
        len(closes) - 1 log returns (empty if fewer than two closes).

    Raises:
        ValueError: if any close is <= 0 (no real log return exists).
    """
    if any(c <= 0 for c in closes):
        raise ValueError("closes must all be > 0 to take log returns")
    return [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]


def annualized_realized_vol(
    window_returns: Sequence[float],
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized realized vol of one window of log returns.

    Sample standard deviation (mean-subtracted, ddof = 1) of the returns, scaled
    by sqrt(trading_days). The decimal result (0.20 = 20%) matches the units of
    the implied volatilities it is compared against.

    Args:
        window_returns: the log returns in the window; at least two are needed
            for a sample standard deviation.
        trading_days: annualization factor's argument; defaults to 252.

    Raises:
        ValueError: if fewer than two returns are supplied.
    """
    if len(window_returns) < 2:
        raise ValueError(
            "need at least two returns for a sample standard deviation")
    return statistics.stdev(window_returns) * math.sqrt(trading_days)


def rolling_realized_vol(
    closes: Sequence[float],
    window: int = DEFAULT_WINDOW_TRADING_DAYS,
    trading_days: int = TRADING_DAYS_PER_YEAR,
) -> list[float | None]:
    """Rolling annualized realized vol, aligned element-for-element to ``closes``.

    For each close at index ``i`` the value is the annualized realized vol of the
    ``window`` log returns ending at that close (i.e. spanning closes
    ``i - window`` .. ``i``). The first ``window`` entries are ``None`` -- there
    are not yet enough returns to fill the window -- so the returned list has the
    same length as ``closes`` and lines up with its dates without any off-by-one.

    Args:
        closes: daily closing prices in chronological order, all > 0.
        window: number of trailing log returns per estimate (trading days).
        trading_days: annualization factor's argument; defaults to 252.

    Returns:
        A list of length ``len(closes)``: ``None`` where the window cannot be
        filled, otherwise the annualized realized vol (decimal) at that date.

    Raises:
        ValueError: if ``window`` < 2 or any close is <= 0.
    """
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    n = len(closes)
    returns = log_returns(closes)  # length n - 1; returns[j] ends at close j+1
    out: list[float | None] = [None] * n
    for i in range(window, n):
        # The window of `window` returns ending at close i is returns[i-window:i]
        # (return index i-1 is the step into close i).
        out[i] = annualized_realized_vol(returns[i - window:i], trading_days)
    return out
