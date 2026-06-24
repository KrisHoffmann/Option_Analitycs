"""Validation of the continuous-dividend (Merton) extension to BSM.

Covers, per the milestone:
  1. q = 0 reproduces the original no-dividend BSM exactly (backwards compatible).
  2. Put-call parity in its dividend form: C - P = S·e^(-qT) - K·e^(-rT).
  3. Every analytical Greek still matches a finite-difference of the price when
     q > 0 (the dividend terms in delta/gamma/vega/theta are self-consistent).
  4. Dividends move price and delta in the correct direction: a call's value and
     delta fall as q rises, a put's value rises; the option's sensitivity to q
     has opposite sign for calls and puts.

Note on "delta changes sign for high-dividend stocks": a European call delta
(e^(-qT)·N(d1)) stays positive and a put delta stays negative for any q, so delta
itself does not flip sign. The economically meaningful sign change is in the
*dividend sensitivity* ∂Price/∂q — negative for calls, positive for puts — which
test 4 checks directly.
"""

import math

import pytest

from pricing.black_scholes import price, price_and_greeks

SPOTS = [80.0, 100.0, 120.0]
STRIKES = [90.0, 100.0, 110.0]
EXPIRIES = [0.25, 1.0, 2.0]
RATES = [0.0, 0.03, 0.06]
VOLS = [0.15, 0.30]
DIVS = [0.0, 0.02, 0.05, 0.08]


def _grid():
    for option_type in ("call", "put"):
        for s in SPOTS:
            for k in STRIKES:
                for t in EXPIRIES:
                    for r in RATES:
                        for vol in VOLS:
                            for q in DIVS:
                                yield option_type, s, k, t, r, vol, q


# ---------------------------------------------------------------------------
# 1. q = 0 reproduces the original BSM exactly
# ---------------------------------------------------------------------------
def test_zero_dividend_matches_no_dividend_default():
    for option_type in ("call", "put"):
        for s in SPOTS:
            for k in STRIKES:
                explicit = price_and_greeks(option_type, s, k, 1.0, 0.05, 0.2, 0.0)
                default = price_and_greeks(option_type, s, k, 1.0, 0.05, 0.2)
                assert explicit == default  # frozen dataclass equality, exact


def test_zero_dividend_recovers_hull_value():
    # The cited Hull example must be unchanged at q = 0.
    hull = price("call", 42, 40, 0.5, 0.10, 0.20, 0.0)
    assert hull == pytest.approx(4.7594, abs=5e-3)


# ---------------------------------------------------------------------------
# 2. Put-call parity with dividends
# ---------------------------------------------------------------------------
def test_put_call_parity_with_dividends():
    for _, s, k, t, r, vol, q in _grid():
        call = price("call", s, k, t, r, vol, q)
        put = price("put", s, k, t, r, vol, q)
        expected = s * math.exp(-q * t) - k * math.exp(-r * t)
        assert (call - put) == pytest.approx(expected, abs=1e-9, rel=1e-9)


# ---------------------------------------------------------------------------
# 3. Greeks vs finite difference with q > 0
# ---------------------------------------------------------------------------
Q = 0.05


def _p(option_type, s, k, t, r, vol):
    return price(option_type, s, k, t, r, vol, Q)


def _fd_grid():
    for option_type in ("call", "put"):
        for s in (80.0, 100.0, 120.0):
            for k in (90.0, 100.0, 110.0):
                for t in (0.5, 1.5):
                    for r in (0.0, 0.05):
                        for vol in (0.2, 0.4):
                            yield option_type, s, k, t, r, vol


def test_delta_matches_fd_with_dividends():
    for ot, s, k, t, r, vol in _fd_grid():
        h = 1e-4 * s
        fd = (_p(ot, s + h, k, t, r, vol) - _p(ot, s - h, k, t, r, vol)) / (2 * h)
        analytic = price_and_greeks(ot, s, k, t, r, vol, Q).delta
        assert analytic == pytest.approx(fd, abs=1e-6, rel=1e-5)


def test_gamma_matches_fd_with_dividends():
    for ot, s, k, t, r, vol in _fd_grid():
        h = 1e-4 * s
        d_up = price_and_greeks(ot, s + h, k, t, r, vol, Q).delta
        d_dn = price_and_greeks(ot, s - h, k, t, r, vol, Q).delta
        fd = (d_up - d_dn) / (2 * h)
        analytic = price_and_greeks(ot, s, k, t, r, vol, Q).gamma
        assert analytic == pytest.approx(fd, abs=1e-7, rel=1e-5)


def test_vega_matches_fd_with_dividends():
    for ot, s, k, t, r, vol in _fd_grid():
        h = 1e-4
        fd = (_p(ot, s, k, t, r, vol + h) - _p(ot, s, k, t, r, vol - h)) / (2 * h)
        analytic = price_and_greeks(ot, s, k, t, r, vol, Q).vega
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


def test_theta_matches_fd_with_dividends():
    for ot, s, k, t, r, vol in _fd_grid():
        h = 1e-5
        fd = -(_p(ot, s, k, t + h, r, vol) - _p(ot, s, k, t - h, r, vol)) / (2 * h)
        analytic = price_and_greeks(ot, s, k, t, r, vol, Q).theta
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


def test_rho_matches_fd_with_dividends():
    for ot, s, k, t, r, vol in _fd_grid():
        h = 1e-5
        fd = (_p(ot, s, k, t, r + h, vol) - _p(ot, s, k, t, r - h, vol)) / (2 * h)
        analytic = price_and_greeks(ot, s, k, t, r, vol, Q).rho
        assert analytic == pytest.approx(fd, abs=1e-4, rel=1e-5)


# ---------------------------------------------------------------------------
# 4. Dividends move price and delta in the correct direction
# ---------------------------------------------------------------------------
def test_call_value_and_delta_fall_as_dividends_rise():
    base = dict(spot=100, strike=100, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.25)
    prev = price_and_greeks("call", **base, dividend_yield=0.0)
    for q in (0.02, 0.05, 0.10):
        cur = price_and_greeks("call", **base, dividend_yield=q)
        assert cur.price < prev.price
        assert cur.delta < prev.delta
        prev = cur


def test_put_value_rises_as_dividends_rise():
    base = dict(spot=100, strike=100, time_to_expiry=1.0, risk_free_rate=0.05,
                volatility=0.25)
    prev = price("put", **base, dividend_yield=0.0)
    for q in (0.02, 0.05, 0.10):
        cur = price("put", **base, dividend_yield=q)
        assert cur > prev
        prev = cur


def test_dividend_sensitivity_has_opposite_sign_for_call_and_put():
    # epsilon = dPrice/dq: negative for a call, positive for a put.
    h = 1e-5
    for option_type, sign in (("call", -1), ("put", 1)):
        up = price(option_type, 100, 100, 1.0, 0.05, 0.25, 0.05 + h)
        dn = price(option_type, 100, 100, 1.0, 0.05, 0.25, 0.05 - h)
        d_price_dq = (up - dn) / (2 * h)
        assert math.copysign(1, d_price_dq) == sign
