"""Validation of the Black-Scholes-Merton engine against external references.

Per docs/finance-standards.md, no pricing code is "done" until it is checked
against something independent. This file covers, in order:

  1. A cited textbook value (Hull) for price and delta.
  2. Put-call parity, asserted across a grid of inputs.
  3. Every analytical Greek vs. a central finite-difference of the price.
  4. The degenerate boundaries T -> 0 and sigma -> 0.
  5. Input validation.

The finite-difference checks are the sanctioned way to validate the Greeks: if
the closed-form Greek and the bumped-price difference disagree, one is wrong.
"""

import math
from dataclasses import FrozenInstanceError

import pytest

from pricing.black_scholes import (
    BlackScholesResult,
    price,
    price_and_greeks,
)

# A grid spanning ITM/ATM/OTM, short/long expiry, zero/positive rates, and
# low/high vol. Reused by the parity and finite-difference tests.
SPOTS = [80.0, 100.0, 120.0]
STRIKES = [90.0, 100.0, 110.0]
EXPIRIES = [0.25, 1.0, 2.0]
RATES = [0.0, 0.03, 0.05]
VOLS = [0.10, 0.20, 0.40]


def _grid():
    for option_type in ("call", "put"):
        for spot in SPOTS:
            for strike in STRIKES:
                for time_to_expiry in EXPIRIES:
                    for rate in RATES:
                        for vol in VOLS:
                            yield option_type, spot, strike, time_to_expiry, rate, vol


# ---------------------------------------------------------------------------
# 1. Cited textbook reference
# ---------------------------------------------------------------------------
# Reference: John C. Hull, "Options, Futures, and Other Derivatives" (worked
# example for a European option on a non-dividend-paying stock):
#   S = 42, K = 40, r = 0.10, sigma = 0.20, T = 0.5
#   -> call = 4.76, put = 0.81, call delta = N(d1) = 0.779.
HULL = dict(spot=42.0, strike=40.0, time_to_expiry=0.5,
            risk_free_rate=0.10, volatility=0.20)


def test_reference_price_matches_hull():
    call = price_and_greeks("call", **HULL)
    put = price_and_greeks("put", **HULL)
    assert call.price == pytest.approx(4.76, abs=5e-3)
    assert put.price == pytest.approx(0.81, abs=5e-3)


def test_reference_delta_matches_hull():
    call = price_and_greeks("call", **HULL)
    put = price_and_greeks("put", **HULL)
    assert call.delta == pytest.approx(0.779, abs=5e-3)
    # Put delta = call delta - 1 (a consequence of put-call parity).
    assert put.delta == pytest.approx(call.delta - 1.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 2. Put-call parity:  C - P = S - K e^{-rT}   (no dividends)
# ---------------------------------------------------------------------------
def test_put_call_parity_across_grid():
    for _, spot, strike, t, r, vol in _grid():
        call = price("call", spot, strike, t, r, vol)
        put = price("put", spot, strike, t, r, vol)
        expected = spot - strike * math.exp(-r * t)
        assert (call - put) == pytest.approx(expected, abs=1e-9, rel=1e-9)


# ---------------------------------------------------------------------------
# 3. Greeks vs. central finite difference of the price
# ---------------------------------------------------------------------------
def _price(option_type, spot, strike, t, r, vol) -> float:
    return price(option_type, spot, strike, t, r, vol)


def test_delta_matches_finite_difference():
    for option_type, spot, strike, t, r, vol in _grid():
        h = 1e-4 * spot
        fd = (_price(option_type, spot + h, strike, t, r, vol)
              - _price(option_type, spot - h, strike, t, r, vol)) / (2 * h)
        analytic = price_and_greeks(option_type, spot, strike, t, r, vol).delta
        assert analytic == pytest.approx(fd, abs=1e-6, rel=1e-5)


def _delta(option_type, spot, strike, t, r, vol) -> float:
    return price_and_greeks(option_type, spot, strike, t, r, vol).delta


def test_gamma_matches_finite_difference():
    # Gamma = d(delta)/d(spot). We central-difference delta rather than taking a
    # second difference of the price: delta is itself validated against the price
    # FD above, and differencing it once is far more numerically stable than a
    # raw second difference (which suffers large truncation error on the sharply
    # curved short-expiry, low-vol cases in the grid).
    for option_type, spot, strike, t, r, vol in _grid():
        h = 1e-4 * spot
        fd = (_delta(option_type, spot + h, strike, t, r, vol)
              - _delta(option_type, spot - h, strike, t, r, vol)) / (2 * h)
        analytic = price_and_greeks(option_type, spot, strike, t, r, vol).gamma
        assert analytic == pytest.approx(fd, abs=1e-7, rel=1e-5)


def test_vega_matches_finite_difference():
    for option_type, spot, strike, t, r, vol in _grid():
        h = 1e-4
        fd = (_price(option_type, spot, strike, t, r, vol + h)
              - _price(option_type, spot, strike, t, r, vol - h)) / (2 * h)
        analytic = price_and_greeks(option_type, spot, strike, t, r, vol).vega
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


def test_rho_matches_finite_difference():
    for option_type, spot, strike, t, r, vol in _grid():
        h = 1e-5
        fd = (_price(option_type, spot, strike, t, r + h, vol)
              - _price(option_type, spot, strike, t, r - h, vol)) / (2 * h)
        analytic = price_and_greeks(option_type, spot, strike, t, r, vol).rho
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


def test_theta_matches_finite_difference():
    # theta is dV/d(calendar time) = -dV/dT, so the FD bumps T and negates.
    for option_type, spot, strike, t, r, vol in _grid():
        h = 1e-5
        fd = -(_price(option_type, spot, strike, t + h, r, vol)
               - _price(option_type, spot, strike, t - h, r, vol)) / (2 * h)
        analytic = price_and_greeks(option_type, spot, strike, t, r, vol).theta
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


# ---------------------------------------------------------------------------
# 4. Edge cases: T -> 0 and sigma -> 0 (no division by zero, no NaN)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spot,strike", [(110.0, 100.0), (90.0, 100.0), (100.0, 100.0)])
def test_expiry_returns_intrinsic(spot, strike):
    call = price_and_greeks("call", spot, strike, 0.0, 0.05, 0.20)
    put = price_and_greeks("put", spot, strike, 0.0, 0.05, 0.20)
    assert call.price == pytest.approx(max(spot - strike, 0.0))
    assert put.price == pytest.approx(max(strike - spot, 0.0))
    # No Greek is NaN/inf at the boundary.
    for result in (call, put):
        for value in (result.delta, result.gamma, result.theta,
                      result.vega, result.rho):
            assert math.isfinite(value)


def test_expiry_is_continuous_limit():
    # The T -> 0 guard must agree with the analytic formula as T shrinks.
    common = dict(spot=110.0, strike=100.0, risk_free_rate=0.05, volatility=0.20)
    near = price("call", time_to_expiry=1e-7, **common)
    at = price("call", time_to_expiry=0.0, **common)
    assert near == pytest.approx(at, abs=1e-3)


@pytest.mark.parametrize("spot,strike", [(110.0, 100.0), (90.0, 100.0)])
def test_zero_vol_returns_discounted_intrinsic(spot, strike):
    r, t = 0.05, 1.0
    discounted_strike = strike * math.exp(-r * t)
    call = price_and_greeks("call", spot, strike, t, r, 0.0)
    put = price_and_greeks("put", spot, strike, t, r, 0.0)
    assert call.price == pytest.approx(max(spot - discounted_strike, 0.0))
    assert put.price == pytest.approx(max(discounted_strike - spot, 0.0))


def test_zero_vol_is_continuous_limit():
    # As sigma -> 0+, the analytic price must approach the sigma == 0 guard.
    common = dict(spot=110.0, strike=100.0, time_to_expiry=1.0, risk_free_rate=0.05)
    near = price("call", volatility=1e-7, **common)
    at = price("call", volatility=0.0, **common)
    assert near == pytest.approx(at, abs=1e-3)


# ---------------------------------------------------------------------------
# 5. Input validation
# ---------------------------------------------------------------------------
# (option_type, spot, strike, time_to_expiry, risk_free_rate, volatility), each
# row violating exactly one input guard.
@pytest.mark.parametrize("args", [
    ("buy", 100, 100, 1.0, 0.05, 0.2),    # bad option type
    ("call", 0, 100, 1.0, 0.05, 0.2),     # non-positive spot
    ("call", 100, -5, 1.0, 0.05, 0.2),    # non-positive strike
    ("call", 100, 100, -1.0, 0.05, 0.2),  # negative time
    ("call", 100, 100, 1.0, 0.05, -0.2),  # negative volatility
])
def test_invalid_inputs_raise(args):
    with pytest.raises(ValueError):
        price_and_greeks(*args)


def test_result_is_immutable():
    result = price_and_greeks("call", 100, 100, 1.0, 0.05, 0.2)
    assert isinstance(result, BlackScholesResult)
    with pytest.raises(FrozenInstanceError):
        result.price = 0.0  # frozen dataclass
