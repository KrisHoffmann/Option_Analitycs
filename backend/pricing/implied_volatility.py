"""Implied-volatility solver: back out the volatility that reprices a European
option to an observed market price, under the same BSM assumptions as
``black_scholes`` (European exercise, constant rate, Merton continuous dividend
yield ``q``).

Method (stated here and in the README, per docs/finance-standards.md):

    Newton-Raphson on price(sigma) - target, seeded at a reasonable guess and
    using the closed-form vega as the derivative, with a Brent bisection
    fallback. Newton is fast and, because vega > 0 everywhere the price is
    sensitive to vol, usually converges in a handful of steps. But vega
    collapses toward zero for deep in/out-of-the-money options and very short
    expiries, where Newton can stall or step out of bounds. When that happens we
    fall back to Brent's method on a bracketed interval, which is slower but
    guaranteed to converge given a sign change.

Failure is explicit. The solver raises ``ImpliedVolatilityError`` rather than
returning a silent NaN or a wrong number when:

    - the target price is below intrinsic value (no real IV exists), or
    - the price exceeds the no-arbitrage upper bound, or
    - neither method converges within tolerance.

Units match ``black_scholes``: rate and the returned vol are decimals; time is
in years.
"""

from __future__ import annotations

import math

from scipy.optimize import brentq

from pricing.black_scholes import OptionType, price, price_and_greeks

# Search bounds for volatility. 1e-4 (0.01%) to 5.0 (500%) brackets every
# realistically quoted option; anything outside is treated as non-convergence.
_MIN_VOL = 1e-4
_MAX_VOL = 5.0
_PRICE_TOL = 1e-8   # absolute price tolerance for "repriced to target"
_MAX_NEWTON_ITERS = 100


class ImpliedVolatilityError(ValueError):
    """Raised when no valid implied volatility can be returned.

    Carries a human-readable reason; the API layer (M4) maps this to a clear
    client error rather than letting a NaN leak through.
    """


def _no_arbitrage_bounds(option_type: OptionType, spot: float, strike: float,
                         time_to_expiry: float, risk_free_rate: float,
                         dividend_yield: float) -> tuple[float, float]:
    """(intrinsic lower bound, upper bound) on a European option's price.

    Below the lower bound or above the upper bound there is no volatility that
    reproduces the price, so the request is rejected. With a continuous dividend
    yield ``q`` the spot is dividend-discounted (S·e^{-qT}) in both bounds.
    """
    dividend_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry)
    if option_type == "call":
        # max(S e^{-qT} - K e^{-rT}, 0) <= C <= S e^{-qT}
        lower = max(dividend_spot - discounted_strike, 0.0)
        upper = dividend_spot
    else:
        # max(K e^{-rT} - S e^{-qT}, 0) <= P <= K e^{-rT}
        lower = max(discounted_strike - dividend_spot, 0.0)
        upper = discounted_strike
    return lower, upper


def implied_volatility(option_type: OptionType, market_price: float, spot: float,
                       strike: float, time_to_expiry: float,
                       risk_free_rate: float, dividend_yield: float = 0.0
                       ) -> float:
    """Solve for the BSM implied volatility that reprices to ``market_price``.

    Args:
        option_type: "call" or "put".
        market_price: observed option price to match.
        spot, strike: > 0.
        time_to_expiry: years, > 0 (a fully expired option has no IV).
        risk_free_rate: annual, continuously compounded, decimal.
        dividend_yield: continuous dividend yield q (decimal); default 0
            reproduces the original no-dividend BSM exactly.

    Returns:
        Implied volatility as a decimal (e.g. 0.23 for 23%).

    Raises:
        ImpliedVolatilityError: price below intrinsic / above the no-arbitrage
            bound, expired option, or non-convergence.
        ValueError: on structurally invalid inputs (non-positive spot/strike),
            surfaced from the pricing layer.
    """
    if time_to_expiry <= 0:
        raise ImpliedVolatilityError(
            "time_to_expiry must be > 0 to imply a volatility")
    if market_price <= 0:
        raise ImpliedVolatilityError(
            f"market_price must be > 0, got {market_price}")

    lower_bound, upper_bound = _no_arbitrage_bounds(
        option_type, spot, strike, time_to_expiry, risk_free_rate, dividend_yield)
    # A tiny tolerance lets a price sitting exactly on intrinsic resolve to ~0
    # vol instead of being rejected by floating-point noise.
    if market_price < lower_bound - _PRICE_TOL:
        raise ImpliedVolatilityError(
            f"market_price {market_price} is below intrinsic value "
            f"{lower_bound:.6f}; no real implied volatility exists")
    if market_price > upper_bound + _PRICE_TOL:
        raise ImpliedVolatilityError(
            f"market_price {market_price} exceeds the no-arbitrage upper bound "
            f"{upper_bound:.6f}")
    # A price sitting on intrinsic value has no time value, so its implied
    # volatility is zero under the model. The true root is below the search
    # bracket, so we return it directly rather than failing to bracket it.
    if market_price <= lower_bound + _PRICE_TOL:
        return 0.0

    def objective(vol: float) -> float:
        return price(option_type, spot, strike, time_to_expiry,
                     risk_free_rate, vol, dividend_yield) - market_price

    newton = _try_newton(option_type, market_price, spot, strike,
                         time_to_expiry, risk_free_rate, dividend_yield)
    if newton is not None:
        return newton

    # Newton stalled or stepped out of bounds; fall back to Brent on the full
    # vol bracket. Require a sign change across the interval first.
    if objective(_MIN_VOL) * objective(_MAX_VOL) > 0:
        raise ImpliedVolatilityError(
            "implied volatility did not converge: no sign change across the "
            f"search bracket [{_MIN_VOL}, {_MAX_VOL}] (price may be at a "
            "numerical boundary)")
    try:
        return float(brentq(objective, _MIN_VOL, _MAX_VOL, xtol=1e-10,
                            maxiter=_MAX_NEWTON_ITERS))
    except (RuntimeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ImpliedVolatilityError(
            f"implied volatility did not converge: {exc}") from exc


def _try_newton(option_type: OptionType, market_price: float, spot: float,
                strike: float, time_to_expiry: float, risk_free_rate: float,
                dividend_yield: float) -> float | None:
    """One Newton-Raphson attempt. Returns the IV, or None if it fails to
    converge cleanly (so the caller can fall back to Brent).

    Seed: Brenner-Subrahmanyam approximation for an at-the-money option,
    sigma ~ sqrt(2*pi/T) * price/spot, clamped into the search bounds. It is a
    good starting point near the money and harmless elsewhere.
    """
    vol = math.sqrt(2 * math.pi / time_to_expiry) * market_price / spot
    vol = min(max(vol, _MIN_VOL), _MAX_VOL)

    for _ in range(_MAX_NEWTON_ITERS):
        result = price_and_greeks(option_type, spot, strike, time_to_expiry,
                                  risk_free_rate, vol, dividend_yield)
        diff = result.price - market_price
        if abs(diff) < _PRICE_TOL:
            return vol
        # vega is dPrice/dsigma; near-zero vega means Newton is unreliable here.
        if result.vega < 1e-8:
            return None
        vol -= diff / result.vega
        if not (_MIN_VOL <= vol <= _MAX_VOL):
            return None  # stepped out of bounds; let Brent handle it
    return None
