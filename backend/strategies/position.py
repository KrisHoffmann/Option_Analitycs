"""The multi-leg position model and its core computations: payoff-at-expiry,
current (pre-expiry) value, and aggregated net Greeks.

Pure math built on ``pricing.black_scholes`` (see docs/architecture.md). The net
Greeks are a first-class function here, not an afterthought in the UI: the
insight in a multi-leg position is the *net* delta/gamma/theta/vega/rho, not the
per-leg numbers.

Leg model
---------
A leg is one of:
  - an option   : instrument "call"/"put", with a strike and a time_to_expiry, or
  - the underlying: instrument "underlying", with no strike/expiry.
The underlying leg exists so strategies that hold stock (e.g. a covered call)
can be modelled; the milestone's option-only leg shape is extended deliberately
for exactly that reason.

Conventions and assumptions
---------------------------
  - ``side`` long/short maps to a +1/-1 sign; ``quantity`` (> 0) scales it.
  - Quantity is in contract units priced per single underlying share; the
    100-share contract multiplier is NOT applied here. Apply your contract size
    externally if you need per-contract dollar figures.
  - ``current_value`` and ``net_greeks`` value every leg with a single flat
    ``volatility`` and ``risk_free_rate`` (the BSM constant-vol assumption).
    Per-strike / per-expiry volatilities are a vol-surface concern, out of scope
    for v1.
  - ``payoff_at_expiry`` is the sum of each leg's intrinsic value at the terminal
    spot. For single-expiry strategies (verticals, straddles, condors, covered
    calls) this is the familiar hockey-stick. For multi-expiry strategies
    (calendars) it treats every leg as expiring together, which a calendar does
    NOT do -- read its current-value curve near the near-term expiry instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pricing.black_scholes import price_and_greeks

Instrument = Literal["call", "put", "underlying"]
Side = Literal["long", "short"]


@dataclass(frozen=True)
class Leg:
    """A single position leg. Frozen so a built position can't drift."""

    instrument: Instrument
    quantity: float
    side: Side
    strike: float | None = None
    time_to_expiry: float | None = None

    def __post_init__(self) -> None:
        if self.instrument not in ("call", "put", "underlying"):
            raise ValueError(f"unknown instrument {self.instrument!r}")
        if self.side not in ("long", "short"):
            raise ValueError(f"side must be 'long' or 'short', got {self.side!r}")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity}")
        if self.instrument == "underlying":
            if self.strike is not None or self.time_to_expiry is not None:
                raise ValueError(
                    "an underlying leg has no strike or time_to_expiry")
        else:
            if self.strike is None or self.strike <= 0:
                raise ValueError("an option leg needs a strike > 0")
            if self.time_to_expiry is None or self.time_to_expiry < 0:
                raise ValueError(
                    "an option leg needs a time_to_expiry >= 0 (years)")

    @property
    def sign(self) -> int:
        """+1 for long, -1 for short."""
        return 1 if self.side == "long" else -1

    @property
    def signed_quantity(self) -> float:
        return self.sign * self.quantity


@dataclass(frozen=True)
class Position:
    """An ordered collection of legs, optionally named (e.g. "bull call spread")."""

    legs: tuple[Leg, ...]
    name: str = ""

    def __post_init__(self) -> None:
        if not self.legs:
            raise ValueError("a position needs at least one leg")


@dataclass(frozen=True)
class NetGreeks:
    """Position-level Greeks: the sum of the per-leg Greeks. Units match
    ``pricing.black_scholes`` (delta per $1 spot, vega/rho per 1.00, theta per
    year)."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0


def _leg_intrinsic(leg: Leg, terminal_spot: float) -> float:
    """Unsigned intrinsic value of one leg at a terminal spot (expiry)."""
    if leg.instrument == "underlying":
        return terminal_spot
    if leg.instrument == "call":
        return max(terminal_spot - leg.strike, 0.0)
    return max(leg.strike - terminal_spot, 0.0)


def _leg_model_value(leg: Leg, spot: float, risk_free_rate: float,
                     volatility: float) -> float:
    """Unsigned current (pre-expiry) model value of one leg."""
    if leg.instrument == "underlying":
        return spot
    return price_and_greeks(leg.instrument, spot, leg.strike,
                            leg.time_to_expiry, risk_free_rate, volatility).price


def payoff_at_expiry(position: Position, spot_grid: Sequence[float]) -> list[float]:
    """Position value at expiry (sum of signed leg intrinsics) over the grid.

    See the module docstring on the multi-expiry (calendar) caveat.
    """
    return [
        sum(leg.signed_quantity * _leg_intrinsic(leg, spot) for leg in position.legs)
        for spot in spot_grid
    ]


def current_value(position: Position, spot_grid: Sequence[float],
                  risk_free_rate: float, volatility: float) -> list[float]:
    """Current (pre-expiry) model value of the position over the spot grid.

    Values every leg at a single flat volatility and rate (see assumptions).
    """
    return [
        sum(
            leg.signed_quantity
            * _leg_model_value(leg, spot, risk_free_rate, volatility)
            for leg in position.legs
        )
        for spot in spot_grid
    ]


def net_greeks(position: Position, spot: float, risk_free_rate: float,
               volatility: float) -> NetGreeks:
    """Aggregate the five Greeks across all legs at a single spot.

    The underlying leg contributes delta = signed quantity and zero to the other
    Greeks. Option legs contribute signed_quantity * (closed-form Greek).
    """
    delta = gamma = theta = vega = rho = 0.0
    for leg in position.legs:
        q = leg.signed_quantity
        if leg.instrument == "underlying":
            delta += q  # d(spot)/d(spot) = 1; stock has no gamma/theta/vega/rho
            continue
        g = price_and_greeks(leg.instrument, spot, leg.strike,
                             leg.time_to_expiry, risk_free_rate, volatility)
        delta += q * g.delta
        gamma += q * g.gamma
        theta += q * g.theta
        vega += q * g.vega
        rho += q * g.rho
    return NetGreeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)
