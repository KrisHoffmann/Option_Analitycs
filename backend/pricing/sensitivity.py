"""Greek-sensitivity series: how price or a Greek responds as one pricing input
is swept over a range, holding the rest fixed.

Pure and tested here so the API route that exposes it (M4) stays thin, and so
the frontend's Greek-sensitivity view (M7) has a validated engine underneath.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pricing.black_scholes import OptionType, price_and_greeks

# The pricing input being varied. Each name is a keyword of price_and_greeks.
SensitivityVariable = Literal[
    "spot", "strike", "time_to_expiry", "risk_free_rate", "volatility"
]
# The output being tracked. Each is an attribute of BlackScholesResult.
SensitivityMetric = Literal["price", "delta", "gamma", "theta", "vega", "rho"]


def evenly_spaced(start: float, stop: float, num_points: int) -> list[float]:
    """``num_points`` evenly spaced values from start to stop, inclusive.

    A small dependency-free linspace, used for both the payoff spot grid and the
    sensitivity sweep so neither the routes nor this module need numpy for grid
    construction.
    """
    if num_points < 2:
        raise ValueError("num_points must be >= 2")
    if stop <= start:
        raise ValueError("stop must be > start")
    step = (stop - start) / (num_points - 1)
    return [start + step * i for i in range(num_points)]


def sensitivity_series(
    option_type: OptionType,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    *,
    variable: SensitivityVariable,
    metric: SensitivityMetric,
    variable_values: Sequence[float],
) -> list[float]:
    """Evaluate ``metric`` at each value of ``variable``, holding other inputs fixed.

    Args:
        option_type ... volatility: the base contract.
        variable: which input to sweep.
        metric: which output (price or a Greek) to record.
        variable_values: the values of ``variable`` to evaluate at.

    Returns:
        The metric values, aligned one-to-one with ``variable_values``.
    """
    base = dict(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        risk_free_rate=risk_free_rate,
        volatility=volatility,
    )
    series: list[float] = []
    for value in variable_values:
        params = {**base, variable: value}
        result = price_and_greeks(option_type, **params)
        series.append(getattr(result, metric))
    return series
