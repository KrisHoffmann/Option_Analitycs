"""Validation of the multi-leg strategy engine (M3).

Two kinds of check, per the milestone:
  1. Net Greeks equal the sum of the per-leg Greeks (the defining property of
     the aggregation), across the named strategies.
  2. Known payoff-at-expiry bounds for each named strategy (a vertical caps at
     its width, a covered call caps at its strike, an iron condor's gross payoff
     peaks at zero, etc.).
Plus leg/constructor validation and the current-value -> intrinsic limit.
"""

import pytest

from pricing.black_scholes import price_and_greeks
from strategies.library import (
    calendar_spread,
    covered_call,
    iron_condor,
    straddle,
    strangle,
    vertical_spread,
)
from strategies.position import (
    Leg,
    Position,
    current_value,
    net_greeks,
    payoff_at_expiry,
)

R, VOL = 0.04, 0.25
GRID = [50.0 + i for i in range(0, 101)]  # 50 .. 150 inclusive


def _manual_net_greeks(position, spot, r, vol):
    """Independently sum the per-leg Greeks, the way the engine should."""
    totals = dict(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)
    for leg in position.legs:
        q = leg.signed_quantity
        if leg.instrument == "underlying":
            totals["delta"] += q
            continue
        g = price_and_greeks(leg.instrument, spot, leg.strike,
                             leg.time_to_expiry, r, vol)
        totals["delta"] += q * g.delta
        totals["gamma"] += q * g.gamma
        totals["theta"] += q * g.theta
        totals["vega"] += q * g.vega
        totals["rho"] += q * g.rho
    return totals


@pytest.fixture
def named_positions():
    return [
        vertical_spread("call", 95, 105, 0.5),
        vertical_spread("put", 105, 95, 0.5),
        straddle(100, 0.5),
        strangle(90, 110, 0.5),
        calendar_spread("call", 100, 0.25, 0.75),
        covered_call(105, 0.5),
        iron_condor(80, 90, 110, 120, 0.5),
    ]


# ---------------------------------------------------------------------------
# 1. Net Greeks == sum of leg Greeks
# ---------------------------------------------------------------------------
def test_net_greeks_equal_sum_of_leg_greeks(named_positions):
    spot = 100.0
    for position in named_positions:
        net = net_greeks(position, spot, R, VOL)
        manual = _manual_net_greeks(position, spot, R, VOL)
        assert net.delta == pytest.approx(manual["delta"])
        assert net.gamma == pytest.approx(manual["gamma"])
        assert net.theta == pytest.approx(manual["theta"])
        assert net.vega == pytest.approx(manual["vega"])
        assert net.rho == pytest.approx(manual["rho"])


def test_underlying_leg_contributes_unit_delta_only():
    position = Position(legs=(Leg("underlying", 3, "long"),))
    net = net_greeks(position, 100.0, R, VOL)
    assert net.delta == pytest.approx(3.0)
    assert (net.gamma, net.theta, net.vega, net.rho) == (0.0, 0.0, 0.0, 0.0)


def test_short_leg_flips_greek_sign():
    long_call = net_greeks(
        Position(legs=(Leg("call", 1, "long", 100, 0.5),)), 100, R, VOL)
    short_call = net_greeks(
        Position(legs=(Leg("call", 1, "short", 100, 0.5),)), 100, R, VOL)
    assert short_call.delta == pytest.approx(-long_call.delta)
    assert short_call.vega == pytest.approx(-long_call.vega)


# ---------------------------------------------------------------------------
# 2. Known payoff-at-expiry bounds
# ---------------------------------------------------------------------------
def test_bull_call_spread_payoff_bounded_by_width():
    # long 95 call / short 105 call: payoff in [0, width=10].
    payoffs = payoff_at_expiry(vertical_spread("call", 95, 105, 0.5), GRID)
    assert min(payoffs) == pytest.approx(0.0)
    assert max(payoffs) == pytest.approx(10.0)
    # Below the long strike it is worthless; above the short strike it caps.
    assert payoff_at_expiry(vertical_spread("call", 95, 105, 0.5), [80.0])[0] == 0.0
    assert payoff_at_expiry(vertical_spread("call", 95, 105, 0.5), [140.0])[0] == \
        pytest.approx(10.0)


def test_covered_call_payoff_capped_at_strike():
    # long underlying + short 105 call = min(S, 105).
    pos = covered_call(105, 0.5)
    payoffs = payoff_at_expiry(pos, GRID)
    assert max(payoffs) == pytest.approx(105.0)
    assert payoff_at_expiry(pos, [60.0])[0] == pytest.approx(60.0)   # = spot
    assert payoff_at_expiry(pos, [140.0])[0] == pytest.approx(105.0)  # capped


def test_long_straddle_payoff_is_absolute_distance():
    pos = straddle(100, 0.5)
    assert payoff_at_expiry(pos, [100.0])[0] == pytest.approx(0.0)
    assert payoff_at_expiry(pos, [130.0])[0] == pytest.approx(30.0)
    assert payoff_at_expiry(pos, [70.0])[0] == pytest.approx(30.0)


def test_iron_condor_gross_payoff_bounds():
    # 80/90/110/120: gross intrinsic peaks at 0 in the body, troughs at -wing.
    pos = iron_condor(80, 90, 110, 120, 0.5)
    payoffs = payoff_at_expiry(pos, GRID)
    assert max(payoffs) == pytest.approx(0.0)
    assert min(payoffs) == pytest.approx(-10.0)
    assert payoff_at_expiry(pos, [100.0])[0] == pytest.approx(0.0)  # body


# ---------------------------------------------------------------------------
# current value collapses to intrinsic as expiry approaches
# ---------------------------------------------------------------------------
def test_current_value_approaches_payoff_near_expiry():
    # Grid points are kept off the strikes: an exactly-at-the-money option holds
    # ~S*sigma*sqrt(T/2pi) of time value even at tiny T, which would otherwise
    # swamp the tolerance at the knife-edge.
    pos = vertical_spread("call", 95, 105, time_to_expiry=1e-7)
    grid = [80.0, 100.0, 120.0, 140.0]
    cv = current_value(pos, grid, R, VOL)
    payoff = payoff_at_expiry(pos, grid)
    for c, p in zip(cv, payoff, strict=True):
        assert c == pytest.approx(p, abs=1e-3)


# ---------------------------------------------------------------------------
# Leg and constructor validation
# ---------------------------------------------------------------------------
def test_underlying_leg_rejects_strike():
    with pytest.raises(ValueError):
        Leg("underlying", 1, "long", strike=100)


def test_option_leg_requires_strike_and_expiry():
    with pytest.raises(ValueError):
        Leg("call", 1, "long")  # no strike/expiry


def test_leg_rejects_nonpositive_quantity():
    with pytest.raises(ValueError):
        Leg("call", 0, "long", 100, 0.5)


def test_empty_position_rejected():
    with pytest.raises(ValueError):
        Position(legs=())


@pytest.mark.parametrize("builder", [
    lambda: strangle(110, 90, 0.5),                  # put_strike >= call_strike
    lambda: iron_condor(90, 80, 110, 120, 0.5),      # mis-ordered strikes
    lambda: calendar_spread("call", 100, 0.75, 0.25),  # near >= far
    lambda: vertical_spread("call", 100, 100, 0.5),  # equal strikes
])
def test_constructors_validate_inputs(builder):
    with pytest.raises(ValueError):
        builder()
