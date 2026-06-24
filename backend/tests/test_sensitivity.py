"""Tests for the Greek-sensitivity engine (pricing/sensitivity.py)."""

import pytest

from pricing.black_scholes import price_and_greeks
from pricing.sensitivity import evenly_spaced, sensitivity_series


def test_evenly_spaced_endpoints_and_count():
    grid = evenly_spaced(80, 120, 5)
    assert grid == [80.0, 90.0, 100.0, 110.0, 120.0]


@pytest.mark.parametrize("bad", [
    lambda: evenly_spaced(80, 120, 1),   # too few points
    lambda: evenly_spaced(120, 80, 5),   # stop <= start
])
def test_evenly_spaced_rejects_bad_range(bad):
    with pytest.raises(ValueError):
        bad()


def test_series_matches_pointwise_pricing():
    # Sweeping spot and recording delta must equal delta computed point by point.
    values = evenly_spaced(80, 120, 9)
    series = sensitivity_series(
        "call", spot=100, strike=100, time_to_expiry=0.5,
        risk_free_rate=0.03, volatility=0.2,
        variable="spot", metric="delta", variable_values=values)
    expected = [
        price_and_greeks("call", v, 100, 0.5, 0.03, 0.2).delta for v in values
    ]
    assert series == pytest.approx(expected)


def test_call_delta_increases_with_spot():
    values = evenly_spaced(60, 140, 20)
    series = sensitivity_series(
        "call", spot=100, strike=100, time_to_expiry=0.5,
        risk_free_rate=0.03, volatility=0.2,
        variable="spot", metric="delta", variable_values=values)
    assert all(b >= a for a, b in zip(series, series[1:], strict=False))
    assert series[0] >= 0.0 and series[-1] <= 1.0


def test_price_metric_supported():
    values = evenly_spaced(0.1, 0.5, 5)
    series = sensitivity_series(
        "put", spot=100, strike=100, time_to_expiry=1.0,
        risk_free_rate=0.03, volatility=0.2,
        variable="volatility", metric="price", variable_values=values)
    # Vega is positive: a put's value rises with volatility.
    assert all(b >= a for a, b in zip(series, series[1:], strict=False))
