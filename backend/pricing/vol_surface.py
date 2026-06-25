"""Build an implied-volatility surface from a market option chain.

Pure: a normalized ``OptionChain`` (our domain type) goes in, a grid of
``(forward log-moneyness, time-to-expiry, implied volatility)`` points comes
out. No network, no file I/O, no globals, no FastAPI imports — the route layer
does the fetching and serialization, this module only does the modeling
(docs/architecture.md). It depends on ``data.chain`` for the input shape, which
is plain data, not I/O.

What the builder does, and why (the design decisions, stated where they apply):

  - **OTM wing only.** For each expiry we keep OTM puts (strike < spot) and OTM
    calls (strike >= spot). The OTM wing is the more liquid side, and OTM
    American options carry negligible early-exercise premium — which is what
    makes fitting *European* BSM IV to these *American* prices defensible. ITM
    contracts are not part of the surface (not counted as quality drops).

  - **Quote selection.** We invert the *mid* of a live two-sided quote, never a
    (possibly stale) last print. A contract is dropped unless it has bid > 0 and
    ask > 0, a relative bid-ask spread within tolerance, and real open interest.
    A staleness cutoff on the last trade date is a backstop only — a tight
    two-sided quote with real OI is itself evidence of a live market, so
    staleness does not fire when the provider omits a trade date.

  - **Forward log-moneyness.** The strike axis is k = ln(K / F) where the
    forward F = S·e^{(r - q)T}. Using the *forward* (not spot) puts every
    expiry's smile vertex at k = 0, so skew and term structure are directly
    comparable across expiries on a heatmap — the whole point of the surface.

  - **Expiry window.** Very-near expiries (T below a floor) are excluded because
    IV is ill-conditioned as T -> 0; the far end is capped. Bounds are named
    constants.

  - **European BSM IV under stated assumptions.** IV comes from our own solver
    (we deliberately ignore the provider's own ``implied_volatility`` field —
    the backend owns all numerics). q is a continuous-yield approximation of
    discrete dividends.

  - **Explicit gaps, no interpolation / no parametric fit.** A filtered-out or
    un-invertible strike simply produces no point. We do not interpolate or fit
    a parametric surface (e.g. SVI) — naive interpolation can introduce
    arbitrage, and an honest gappy cloud beats a smooth fabricated one. The
    per-expiry ``FilterCounts`` records how many contracts were dropped and why.

Units follow ``pricing.black_scholes``: rates/vols are decimals, time is years.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from data.chain import OptionChain, OptionQuote
from pricing.implied_volatility import ImpliedVolatilityError, implied_volatility

# --- Filter thresholds (tunable knobs; tuned so a legible smile survives in the
# OTM wings, where the educational content of the surface lives). ------------
MAX_RELATIVE_SPREAD = 0.25      # drop quotes whose (ask-bid)/mid exceeds this
MIN_OPEN_INTEREST = 10          # drop quotes with thinner open interest
MAX_STALENESS_DAYS = 10.0       # backstop: drop quotes whose last print is older

# --- Expiry window (both ends bounded; named constants). --------------------
MIN_DAYS_TO_EXPIRY = 2          # below this, IV is ill-conditioned as T -> 0
MAX_DAYS_TO_EXPIRY = 365        # cap the far end (LEAPS rarely survive filtering)
_DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class SurfacePoint:
    """One solved, retained point on the surface."""

    option_type: str            # "call" or "put"
    strike: float
    log_moneyness: float        # k = ln(K / F), forward moneyness
    time_to_expiry: float       # years
    implied_volatility: float   # decimal, from our BSM solver
    mid_price: float            # (bid + ask) / 2, the price we inverted
    open_interest: int
    relative_spread: float      # (ask - bid) / mid


@dataclass(frozen=True)
class FilterCounts:
    """Per-expiry tally of OTM candidates and why each was dropped. Makes the
    surface's data quality auditable rather than implicit."""

    candidates: int             # OTM-side contracts considered
    retained: int
    no_two_sided_quote: int
    spread_too_wide: int
    insufficient_open_interest: int
    stale_quote: int
    solver_failed: int


@dataclass(frozen=True)
class ExpirySlice:
    """All retained surface points for one expiry, plus its filter audit."""

    expiry: date
    time_to_expiry: float
    forward: float              # F = S·e^{(r - q)T}
    points: tuple[SurfacePoint, ...]
    filtered: FilterCounts


@dataclass(frozen=True)
class VolSurface:
    """The full surface: a list of expiry slices and the assumptions used."""

    ticker: str
    spot: float
    fetched_at: datetime
    risk_free_rate: float
    dividend_yield: float
    slices: tuple[ExpirySlice, ...]


def _is_otm(quote: OptionQuote, spot: float) -> bool:
    """OTM wing membership: puts below spot, calls at-or-above spot."""
    if quote.option_type == "put":
        return quote.strike < spot
    return quote.strike >= spot


def _is_stale(quote: OptionQuote, fetched_at: datetime,
              max_staleness_days: float) -> bool:
    """True if the contract's last print is older than the cutoff. Missing
    trade dates do not count as stale (the two-sided quote + OI gates already
    establish a live market)."""
    last_trade = quote.last_trade_date
    if last_trade is None:
        return False
    if last_trade.tzinfo is None and fetched_at.tzinfo is not None:
        last_trade = last_trade.replace(tzinfo=fetched_at.tzinfo)
    age_days = (fetched_at - last_trade).total_seconds() / 86400.0
    return age_days > max_staleness_days


def _build_slice(
    expiry: date,
    time_to_expiry: float,
    quotes: list[OptionQuote],
    spot: float,
    forward: float,
    risk_free_rate: float,
    dividend_yield: float,
    fetched_at: datetime,
    *,
    max_relative_spread: float,
    min_open_interest: int,
    max_staleness_days: float,
) -> ExpirySlice:
    """Filter, invert, and assemble one expiry's slice. Pure."""
    points: list[SurfacePoint] = []
    candidates = 0
    no_two_sided = spread_wide = thin_oi = stale = solver_failed = 0

    for quote in quotes:
        if not _is_otm(quote, spot):
            continue  # ITM side is not part of the surface (not a quality drop)
        candidates += 1

        # 1. A real two-sided market is required (no last-price fallback).
        if quote.bid is None or quote.ask is None or quote.bid <= 0 or quote.ask <= 0:
            no_two_sided += 1
            continue
        mid = 0.5 * (quote.bid + quote.ask)

        # 2. Spread must be tight enough that the mid is meaningful.
        relative_spread = (quote.ask - quote.bid) / mid
        if relative_spread > max_relative_spread:
            spread_wide += 1
            continue

        # 3. Liquidity gate (OI, not volume -- volume reads 0 overnight).
        if quote.open_interest is None or quote.open_interest < min_open_interest:
            thin_oi += 1
            continue

        # 4. Staleness backstop.
        if _is_stale(quote, fetched_at, max_staleness_days):
            stale += 1
            continue

        # 5. Invert to BSM IV; an un-invertible quote is an explicit gap.
        try:
            iv = implied_volatility(
                quote.option_type, mid, spot, quote.strike, time_to_expiry,
                risk_free_rate, dividend_yield)
        except (ImpliedVolatilityError, ValueError):
            solver_failed += 1
            continue

        points.append(SurfacePoint(
            option_type=quote.option_type,
            strike=quote.strike,
            log_moneyness=math.log(quote.strike / forward),
            time_to_expiry=time_to_expiry,
            implied_volatility=iv,
            mid_price=mid,
            open_interest=quote.open_interest,
            relative_spread=relative_spread,
        ))

    points.sort(key=lambda p: p.log_moneyness)
    return ExpirySlice(
        expiry=expiry,
        time_to_expiry=time_to_expiry,
        forward=forward,
        points=tuple(points),
        filtered=FilterCounts(
            candidates=candidates,
            retained=len(points),
            no_two_sided_quote=no_two_sided,
            spread_too_wide=spread_wide,
            insufficient_open_interest=thin_oi,
            stale_quote=stale,
            solver_failed=solver_failed,
        ),
    )


def build_vol_surface(
    chain: OptionChain,
    risk_free_rate: float,
    dividend_yield: float,
    *,
    max_relative_spread: float = MAX_RELATIVE_SPREAD,
    min_open_interest: int = MIN_OPEN_INTEREST,
    max_staleness_days: float = MAX_STALENESS_DAYS,
    min_days_to_expiry: int = MIN_DAYS_TO_EXPIRY,
    max_days_to_expiry: int = MAX_DAYS_TO_EXPIRY,
) -> VolSurface:
    """Build an implied-volatility surface from a market chain (pure, no I/O).

    Args:
        chain: a normalized OptionChain (spot, fetched_at, expiries with quotes).
        risk_free_rate: r, annual continuously-compounded, decimal.
        dividend_yield: q, continuous dividend yield, decimal.
        max_relative_spread, min_open_interest, max_staleness_days: quote
            filters (see module constants).
        min_days_to_expiry, max_days_to_expiry: expiry window, both ends.

    Returns:
        VolSurface with one ExpirySlice per in-window expiry. Each slice holds
        the retained (forward-log-moneyness, T, IV) points and a FilterCounts
        audit. Expiries outside the window are omitted; strikes that fail any
        filter are explicit gaps (absent points), never interpolated.
    """
    spot = chain.spot
    min_t = min_days_to_expiry / _DAYS_PER_YEAR
    max_t = max_days_to_expiry / _DAYS_PER_YEAR

    slices: list[ExpirySlice] = []
    for expiry_chain in chain.expiries:
        time_to_expiry = expiry_chain.time_to_expiry
        if time_to_expiry < min_t or time_to_expiry > max_t:
            continue
        forward = spot * math.exp((risk_free_rate - dividend_yield) * time_to_expiry)
        slices.append(_build_slice(
            expiry=expiry_chain.expiry,
            time_to_expiry=time_to_expiry,
            quotes=[*expiry_chain.calls, *expiry_chain.puts],
            spot=spot,
            forward=forward,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            fetched_at=chain.fetched_at,
            max_relative_spread=max_relative_spread,
            min_open_interest=min_open_interest,
            max_staleness_days=max_staleness_days,
        ))

    return VolSurface(
        ticker=chain.ticker,
        spot=spot,
        fetched_at=chain.fetched_at,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        slices=tuple(slices),
    )
