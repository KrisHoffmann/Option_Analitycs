"""Validation of the implied-volatility solver (docs/finance-standards.md).

Covers:
  1. Round-trip: price(sigma) -> solve IV -> recover sigma and re-price the input.
  2. The numerically hard cases the doc calls out: deep ITM/OTM and short expiry.
  3. Explicit failure (raises, never a silent NaN) below intrinsic, above the
     no-arbitrage bound, and on an expired option.
"""

import math

import pytest

from pricing.black_scholes import price
from pricing.implied_volatility import (
    ImpliedVolatilityError,
    implied_volatility,
)

RATES = [0.0, 0.03, 0.05]
TRUE_VOLS = [0.10, 0.20, 0.35, 0.75]


def _roundtrip_cases():
    # Moderate moneyness/expiry where prices are comfortably representable.
    for option_type in ("call", "put"):
        for spot, strike in [(100, 90), (100, 100), (100, 110)]:
            for t in [0.25, 1.0, 2.0]:
                for r in RATES:
                    for true_vol in TRUE_VOLS:
                        yield option_type, spot, strike, t, r, true_vol


def test_roundtrip_recovers_volatility_and_price():
    for option_type, spot, strike, t, r, true_vol in _roundtrip_cases():
        market = price(option_type, spot, strike, t, r, true_vol)
        iv = implied_volatility(option_type, market, spot, strike, t, r)
        assert iv == pytest.approx(true_vol, abs=1e-5)
        # Re-pricing at the solved IV recovers the input price.
        repriced = price(option_type, spot, strike, t, r, iv)
        assert repriced == pytest.approx(market, abs=1e-7)


def test_reference_hull_price_implies_input_vol():
    # The Hull example (S=42,K=40,r=0.10,T=0.5) priced at sigma=0.20 must imply
    # 0.20 back out.
    market = price("call", 42, 40, 0.5, 0.10, 0.20)
    iv = implied_volatility("call", market, 42, 40, 0.5, 0.10)
    assert iv == pytest.approx(0.20, abs=1e-6)


@pytest.mark.parametrize("option_type,spot,strike,t", [
    ("call", 100, 60, 0.10),    # deep in-the-money
    ("call", 100, 140, 0.10),   # deep out-of-the-money
    ("put", 100, 140, 0.10),    # deep in-the-money put
    ("put", 100, 60, 0.10),     # deep out-of-the-money put
    ("call", 100, 100, 0.01),   # very short expiry, at the money
    ("call", 100, 110, 0.02),   # short expiry, out of the money
])
def test_roundtrip_on_hard_cases(option_type, spot, strike, t):
    # These are where Newton's vega collapses and the Brent fallback earns its
    # keep. The well-posed invariant is that re-pricing at the solved IV recovers
    # the input price (asserted tightly). Recovering the *volatility* itself is
    # ill-conditioned here -- when vega is tiny, price barely depends on vol, so
    # IV is genuinely poorly identified (the real reason the doc flags these
    # cases). We assert vol recovery only to a conditioning-appropriate
    # tolerance.
    true_vol = 0.30
    market = price(option_type, spot, strike, t, 0.03, true_vol)
    iv = implied_volatility(option_type, market, spot, strike, t, 0.03)
    repriced = price(option_type, spot, strike, t, 0.03, iv)
    assert repriced == pytest.approx(market, abs=1e-7)
    assert iv == pytest.approx(true_vol, abs=5e-3)


def test_price_below_intrinsic_raises():
    # A call can't trade below S - K e^{-rT}.
    spot, strike, t, r = 100, 80, 1.0, 0.05
    intrinsic = spot - strike * math.exp(-r * t)
    with pytest.raises(ImpliedVolatilityError, match="intrinsic"):
        implied_volatility("call", intrinsic - 1.0, spot, strike, t, r)


def test_price_above_upper_bound_raises():
    # A call can't be worth more than the spot.
    with pytest.raises(ImpliedVolatilityError, match="upper bound"):
        implied_volatility("call", 101.0, 100, 100, 1.0, 0.05)


def test_expired_option_raises():
    with pytest.raises(ImpliedVolatilityError, match="time_to_expiry"):
        implied_volatility("call", 5.0, 100, 100, 0.0, 0.05)


def test_nonpositive_price_raises():
    with pytest.raises(ImpliedVolatilityError, match="market_price"):
        implied_volatility("call", 0.0, 100, 100, 1.0, 0.05)


def test_price_at_intrinsic_resolves_to_zero_vol():
    # Sitting exactly on intrinsic means no time value -> IV is 0, not a failure.
    spot, strike, t, r = 100, 80, 1.0, 0.05
    intrinsic = spot - strike * math.exp(-r * t)
    iv = implied_volatility("call", intrinsic, spot, strike, t, r)
    assert iv == 0.0
