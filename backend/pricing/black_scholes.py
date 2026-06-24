"""Black-Scholes-Merton pricing and Greeks for European options.

Pure scalar math: every function takes numbers and returns numbers. No I/O, no
globals, no network. This is the single source of truth for option pricing in
the project — the frontend never re-implements it (see docs/architecture.md).

Model assumptions (BSM, with Merton's continuous-dividend extension):
  - European exercise (no early exercise). American pricing uses the binomial
    model (see binomial.py).
  - Constant volatility and a constant, continuously-compounded risk-free rate.
  - **Continuous dividend yield q** (the Merton 1973 extension), a decimal,
    default 0. q = 0 reproduces the original no-dividend BSM exactly. q enters
    both the d1/d2 drift (as r - q) and the discount factor applied to the spot
    (e^{-qT}); the call/put formulas become:
        Call = S·e^{-qT}·N(d1) − K·e^{-rT}·N(d2)
        Put  = K·e^{-rT}·N(-d2) − S·e^{-qT}·N(-d1)
        d1 = [ln(S/K) + (r - q + σ²/2)·T] / (σ·√T),  d2 = d1 − σ·√T
  - Frictionless: no transaction costs, taxes, or borrowing constraints.

Units (decimals throughout — never percent; see docs/finance-standards.md):
  - spot, strike            : currency, > 0
  - time_to_expiry          : years (e.g. 0.5 = six months), >= 0
  - risk_free_rate          : annual, continuously compounded, decimal (0.05 = 5%)
  - volatility              : annualized, decimal (0.20 = 20%), >= 0
  - dividend_yield          : annual continuous yield q, decimal (0.03 = 3%)

Greek conventions (each is the raw partial derivative in the input's own units):
  - delta : dV/d(spot)            per 1.0 currency unit of spot
  - gamma : d^2V/d(spot)^2        per 1.0 currency unit of spot, squared
  - vega  : dV/d(volatility)      per 1.00 (i.e. +100 vol points). Divide by 100
                                  for the "per 1% vol" figure usually quoted.
  - theta : dV/d(calendar time)   per year. This is -dV/d(time_to_expiry): the
                                  value lost as one year passes. Divide by 365
                                  for a per-calendar-day figure.
  - rho   : dV/d(risk_free_rate)  per 1.00 (+100 rate points). Divide by 100 for
                                  the "per 1% rate" figure usually quoted.

Keeping the Greeks as raw derivatives (rather than pre-scaling vega/rho by 1/100
or theta by 1/365) is what lets the finite-difference tests validate them
directly: bump the input, central-difference the price, compare.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

OptionType = Literal["call", "put"]


@dataclass(frozen=True)
class BlackScholesResult:
    """Price and the five Greeks for a single European option.

    Units follow the module docstring. Frozen so a result can't be mutated by a
    downstream caller after the fact.
    """

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def _validate(option_type: OptionType, spot: float, strike: float,
              time_to_expiry: float, volatility: float) -> None:
    """Reject inputs that have no financial meaning. Raises ValueError."""
    if option_type not in ("call", "put"):
        raise ValueError(f"option_type must be 'call' or 'put', got {option_type!r}")
    if spot <= 0:
        raise ValueError(f"spot must be > 0, got {spot}")
    if strike <= 0:
        raise ValueError(f"strike must be > 0, got {strike}")
    if time_to_expiry < 0:
        raise ValueError(f"time_to_expiry must be >= 0, got {time_to_expiry}")
    if volatility < 0:
        raise ValueError(f"volatility must be >= 0, got {volatility}")


def _d1_d2(spot: float, strike: float, time_to_expiry: float,
           risk_free_rate: float, volatility: float,
           dividend_yield: float) -> tuple[float, float]:
    """The BSM d1 and d2 terms, with the dividend drift (r - q).

    Caller guarantees volatility > 0 and time_to_expiry > 0 (the degenerate
    boundaries are handled separately, before this is reached, so there is no
    division by zero here).
    """
    vol_root_t = volatility * math.sqrt(time_to_expiry)
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_to_expiry
    ) / vol_root_t
    d2 = d1 - vol_root_t
    return d1, d2


def _degenerate_result(option_type: OptionType, spot: float, strike: float,
                       time_to_expiry: float, risk_free_rate: float,
                       volatility: float,
                       dividend_yield: float) -> BlackScholesResult:
    """Limiting price/Greeks when time_to_expiry == 0 or volatility == 0.

    Both boundaries collapse the lognormal to a point mass, so the option is
    worth its (discounted) intrinsic value and the analytic Greek formulas no
    longer apply. We return the limiting values rather than dividing by zero:

      - time_to_expiry == 0 : price = intrinsic on spot; the only non-zero Greek
        is delta, the step function (the payoff kink at spot == strike is
        non-differentiable and reported as 0).
      - volatility == 0     : the forward is deterministic at spot*e^{(r-q)T}, so
        price = e^{-rT} * intrinsic on that forward = intrinsic comparing the
        dividend-discounted spot (S*e^{-qT}) with the rate-discounted strike;
        delta is the step function times e^{-qT}, other Greeks vanish.
    """
    if time_to_expiry == 0:
        intrinsic = (max(spot - strike, 0.0) if option_type == "call"
                     else max(strike - spot, 0.0))
        if option_type == "call":
            delta = 1.0 if spot > strike else 0.0
        else:
            delta = -1.0 if spot < strike else 0.0
        return BlackScholesResult(price=intrinsic, delta=delta, gamma=0.0,
                                  theta=0.0, vega=0.0, rho=0.0)

    dividend_spot = spot * math.exp(-dividend_yield * time_to_expiry)
    discounted_strike = strike * math.exp(-risk_free_rate * time_to_expiry)
    div_disc = math.exp(-dividend_yield * time_to_expiry)
    if option_type == "call":
        price = max(dividend_spot - discounted_strike, 0.0)
        delta = div_disc if dividend_spot > discounted_strike else 0.0
    else:
        price = max(discounted_strike - dividend_spot, 0.0)
        delta = -div_disc if dividend_spot < discounted_strike else 0.0
    return BlackScholesResult(price=price, delta=delta, gamma=0.0,
                              theta=0.0, vega=0.0, rho=0.0)


def price_and_greeks(option_type: OptionType, spot: float, strike: float,
                     time_to_expiry: float, risk_free_rate: float,
                     volatility: float,
                     dividend_yield: float = 0.0) -> BlackScholesResult:
    """Price a European option and return all five Greeks in one pass.

    See the module docstring for units, sign conventions, and assumptions.

    Args:
        option_type: "call" or "put".
        spot: current underlying price S, > 0.
        strike: strike price K, > 0.
        time_to_expiry: T in years, >= 0.
        risk_free_rate: r, annual continuously-compounded, decimal.
        volatility: sigma, annualized, decimal, >= 0.
        dividend_yield: q, annual continuous dividend yield, decimal. Default 0
            reproduces the original no-dividend BSM exactly.

    Returns:
        BlackScholesResult with price and delta/gamma/theta/vega/rho.

    Raises:
        ValueError: on inputs with no financial meaning (bad type, non-positive
            spot/strike, negative time or volatility).
    """
    _validate(option_type, spot, strike, time_to_expiry, volatility)

    if time_to_expiry == 0 or volatility == 0:
        return _degenerate_result(option_type, spot, strike, time_to_expiry,
                                  risk_free_rate, volatility, dividend_yield)

    d1, d2 = _d1_d2(spot, strike, time_to_expiry, risk_free_rate, volatility,
                    dividend_yield)
    discount = math.exp(-risk_free_rate * time_to_expiry)
    div_disc = math.exp(-dividend_yield * time_to_expiry)
    pdf_d1 = norm.pdf(d1)
    root_t = math.sqrt(time_to_expiry)

    # Gamma and vega are identical for calls and puts; price/delta/theta/rho are
    # not. norm.cdf is the standard normal CDF (Phi); norm.pdf is its density.
    gamma = div_disc * pdf_d1 / (spot * volatility * root_t)
    vega = spot * div_disc * pdf_d1 * root_t

    if option_type == "call":
        price = spot * div_disc * norm.cdf(d1) - strike * discount * norm.cdf(d2)
        delta = div_disc * norm.cdf(d1)
        theta = (
            -(spot * div_disc * pdf_d1 * volatility) / (2.0 * root_t)
            + dividend_yield * spot * div_disc * norm.cdf(d1)
            - risk_free_rate * strike * discount * norm.cdf(d2)
        )
        rho = strike * time_to_expiry * discount * norm.cdf(d2)
    else:
        price = strike * discount * norm.cdf(-d2) - spot * div_disc * norm.cdf(-d1)
        delta = div_disc * (norm.cdf(d1) - 1.0)
        theta = (
            -(spot * div_disc * pdf_d1 * volatility) / (2.0 * root_t)
            - dividend_yield * spot * div_disc * norm.cdf(-d1)
            + risk_free_rate * strike * discount * norm.cdf(-d2)
        )
        rho = -strike * time_to_expiry * discount * norm.cdf(-d2)

    return BlackScholesResult(price=price, delta=delta, gamma=gamma,
                              theta=theta, vega=vega, rho=rho)


def price(option_type: OptionType, spot: float, strike: float,
          time_to_expiry: float, risk_free_rate: float,
          volatility: float, dividend_yield: float = 0.0) -> float:
    """The option price alone. Convenience wrapper over price_and_greeks.

    Used by the IV solver, which needs the price as a function of volatility.
    """
    return price_and_greeks(option_type, spot, strike, time_to_expiry,
                            risk_free_rate, volatility, dividend_yield).price
