"""Validation of the CRR binomial model (docs/finance-standards.md).

References used:
  1. The BSM price itself: CRR European must converge to BSM as steps increase.
  2. An analytical result (Merton, "Theory of Rational Option Pricing", 1973):
     it is never optimal to exercise an American call on a non-dividend-paying
     stock early, so its price equals the European call's. The early-exercise
     premium must be zero.
  3. The American put on an ITM contract with time value carries a positive
     early-exercise premium (early exercise can be optimal for puts).
Plus the T->0 and sigma->0 edge cases and input validation.
"""

import math

import pytest

from pricing.binomial import crr_price
from pricing.black_scholes import price as bsm_price

# ATM-ish reference contracts spanning moneyness.
CONTRACTS = [
    ("call", 100, 100, 1.0, 0.05, 0.20),
    ("put", 100, 100, 1.0, 0.05, 0.20),
    ("call", 100, 90, 0.5, 0.03, 0.30),
    ("put", 100, 110, 0.5, 0.03, 0.30),
    ("call", 100, 110, 2.0, 0.01, 0.25),
]


# ---------------------------------------------------------------------------
# 1. CRR European converges to BSM as steps increase
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("option_type,spot,strike,t,r,vol", CONTRACTS)
def test_crr_european_converges_to_bsm(option_type, spot, strike, t, r, vol):
    bsm = bsm_price(option_type, spot, strike, t, r, vol)
    err = {
        n: abs(crr_price(option_type, spot, strike, t, r, vol, steps=n) - bsm)
        for n in (50, 100, 200)
    }
    # Within a tolerance that tightens with steps...
    assert err[50] < 0.15
    assert err[100] < 0.08
    assert err[200] < 0.04
    # ...and 200 steps is closer to BSM than 50.
    assert err[200] < err[50]


def test_crr_european_high_steps_matches_bsm_closely():
    bsm = bsm_price("call", 100, 100, 1.0, 0.05, 0.20)
    crr = crr_price("call", 100, 100, 1.0, 0.05, 0.20, steps=500)
    assert crr == pytest.approx(bsm, abs=0.02)


# ---------------------------------------------------------------------------
# 2. American call on a non-dividend stock == European (Merton 1973)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("strike", [80, 100, 120])
def test_american_call_equals_european_no_dividend(strike):
    common = dict(spot=100, strike=strike, time_to_expiry=1.0,
                  risk_free_rate=0.05, volatility=0.25, steps=200)
    european = crr_price("call", american=False, **common)
    american = crr_price("call", american=True, **common)
    # Early exercise is never optimal -> zero premium (exact in the tree).
    assert american == pytest.approx(european, abs=1e-9)
    assert american - european == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 3. American put premium > 0 for ITM puts with time value
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("spot,strike", [(85, 100), (90, 100), (70, 100)])
def test_american_put_has_positive_early_exercise_premium(spot, strike):
    common = dict(spot=spot, strike=strike, time_to_expiry=1.0,
                  risk_free_rate=0.06, volatility=0.30, steps=200)
    european = crr_price("put", american=False, **common)
    american = crr_price("put", american=True, **common)
    assert american > european
    assert american - european > 1e-3


# ---------------------------------------------------------------------------
# 4. Edge cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("option_type,spot,strike", [
    ("call", 110, 100), ("put", 90, 100), ("call", 100, 100),
])
def test_expiry_returns_intrinsic(option_type, spot, strike):
    for american in (False, True):
        price = crr_price(option_type, spot, strike, 0.0, 0.05, 0.2,
                          american=american)
        expected = max(spot - strike, 0.0) if option_type == "call" \
            else max(strike - spot, 0.0)
        assert price == pytest.approx(expected)


def test_zero_vol_european_is_discounted_forward_intrinsic():
    spot, strike, r, t = 110, 100, 0.05, 1.0
    forward = spot * math.exp(r * t)
    expected = math.exp(-r * t) * max(forward - strike, 0.0)
    price = crr_price("call", spot, strike, t, r, 0.0, american=False)
    assert price == pytest.approx(expected)
    # Should also match the BSM sigma->0 limit.
    assert price == pytest.approx(bsm_price("call", spot, strike, t, r, 0.0))


# ---------------------------------------------------------------------------
# 5. Validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("args,kwargs", [
    (("buy", 100, 100, 1.0, 0.05, 0.2), {}),
    (("call", 0, 100, 1.0, 0.05, 0.2), {}),
    (("call", 100, 100, 1.0, 0.05, 0.2), {"steps": 0}),
    (("call", 100, 100, -1.0, 0.05, 0.2), {}),
])
def test_invalid_inputs_raise(args, kwargs):
    with pytest.raises(ValueError):
        crr_price(*args, **kwargs)
