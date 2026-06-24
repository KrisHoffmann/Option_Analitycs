"""Cox-Ross-Rubinstein (CRR) binomial option pricing.

Pure scalar math, same contract as ``black_scholes`` (no I/O, no globals). The
binomial model complements BSM in two ways:
  - it converges to the BSM price for European options as the step count grows
    (a useful cross-check on both models), and
  - it prices **American** exercise, which BSM cannot, by testing early exercise
    against the continuation value at every node.

Model: at each of ``steps`` time slices dt = T/steps the underlying moves up by
u = exp(sigma*sqrt(dt)) or down by d = 1/u, under the risk-neutral up-probability
p = (exp((r - q)*dt) - d) / (u - d). Option values are found by backward
induction from expiry, discounting one step at a time.

Step count (default 100): error shrinks roughly like O(1/steps), so more steps
means a more accurate price but O(steps^2) work. 100 steps prices a typical
equity option to about a cent while staying instant; raise it for tighter
agreement with BSM, lower it if you need speed.

Assumptions match BSM otherwise: constant volatility and rate, optional
continuous dividend yield q (default 0 = non-dividend-paying).
"""

from __future__ import annotations

import math
from typing import Literal

OptionType = Literal["call", "put"]


def _validate(option_type: OptionType, spot: float, strike: float,
              time_to_expiry: float, volatility: float, steps: int) -> None:
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
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps}")


def _intrinsic(option_type: OptionType, spot: float, strike: float) -> float:
    if option_type == "call":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def _degenerate(option_type: OptionType, spot: float, strike: float,
                time_to_expiry: float, risk_free_rate: float,
                dividend_yield: float, american: bool) -> float:
    """Limiting value when time_to_expiry == 0 or volatility == 0.

    At T=0 the option is worth its intrinsic value. At sigma=0 the underlying
    grows deterministically to the forward spot*e^{(r-q)T}, so the European value
    is the discounted intrinsic on that forward; an American holder may instead
    exercise now, so its value is the larger of the two.
    """
    if time_to_expiry == 0:
        return _intrinsic(option_type, spot, strike)
    forward = spot * math.exp((risk_free_rate - dividend_yield) * time_to_expiry)
    european = math.exp(-risk_free_rate * time_to_expiry) * _intrinsic(
        option_type, forward, strike)
    if not american:
        return european
    return max(european, _intrinsic(option_type, spot, strike))


def crr_price(option_type: OptionType, spot: float, strike: float,
              time_to_expiry: float, risk_free_rate: float, volatility: float,
              *, steps: int = 100, american: bool = False,
              dividend_yield: float = 0.0) -> float:
    """Price a European or American option with the CRR binomial tree.

    Args:
        option_type: "call" or "put".
        spot, strike: > 0.
        time_to_expiry: years, >= 0.
        risk_free_rate: annual continuously-compounded, decimal.
        volatility: annualized, decimal, >= 0.
        steps: number of tree steps (>= 1). See the module docstring on the
            accuracy/speed tradeoff.
        american: if True, allow early exercise (max of continuation vs. intrinsic
            at each node); if False, European (no early exercise).
        dividend_yield: continuous dividend yield q (decimal); default 0.

    Returns:
        The option price.
    """
    _validate(option_type, spot, strike, time_to_expiry, volatility, steps)

    if time_to_expiry == 0 or volatility == 0:
        return _degenerate(option_type, spot, strike, time_to_expiry,
                           risk_free_rate, dividend_yield, american)

    dt = time_to_expiry / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    discount = math.exp(-risk_free_rate * dt)
    p = (math.exp((risk_free_rate - dividend_yield) * dt) - down) / (up - down)
    q = 1.0 - p

    # Option values at expiry, node j = j up-moves and (steps - j) down-moves.
    values = [
        _intrinsic(option_type, spot * up**j * down ** (steps - j), strike)
        for j in range(steps + 1)
    ]

    # Backward induction. At slice i we overwrite values[0..i] in place.
    for i in range(steps - 1, -1, -1):
        for j in range(i + 1):
            continuation = discount * (p * values[j + 1] + q * values[j])
            if american:
                node_spot = spot * up**j * down ** (i - j)
                values[j] = max(continuation,
                                _intrinsic(option_type, node_spot, strike))
            else:
                values[j] = continuation

    return values[0]
