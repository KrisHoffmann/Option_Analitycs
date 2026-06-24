"""Constructors for the named strategies, each returning a ``Position``.

These are thin assemblers over the leg model in ``position`` -- they encode the
leg structure of each strategy and validate strike ordering, nothing more. All
pricing/Greek/payoff behaviour comes from the engine.

Covered in v1: vertical spreads, straddles, strangles, calendar spreads,
covered calls, iron condors.
"""

from __future__ import annotations

from strategies.position import Instrument, Leg, Position, Side


def vertical_spread(option_type: Instrument, long_strike: float,
                    short_strike: float, time_to_expiry: float,
                    quantity: float = 1.0) -> Position:
    """Long one option and short another of the same type and expiry at a
    different strike.

    Works for all four verticals via the strike choice:
      - bull call spread: calls, long_strike < short_strike
      - bear call spread: calls, long_strike > short_strike
      - bull put spread : puts,  long_strike < short_strike
      - bear put spread : puts,  long_strike > short_strike
    """
    if option_type not in ("call", "put"):
        raise ValueError("a vertical spread is built from calls or puts")
    if long_strike == short_strike:
        raise ValueError("a vertical spread needs two different strikes")
    name = f"{option_type} vertical {long_strike}/{short_strike}"
    return Position(
        legs=(
            Leg(option_type, quantity, "long", long_strike, time_to_expiry),
            Leg(option_type, quantity, "short", short_strike, time_to_expiry),
        ),
        name=name,
    )


def straddle(strike: float, time_to_expiry: float, side: Side = "long",
             quantity: float = 1.0) -> Position:
    """A call and a put at the same strike and expiry (long or short both)."""
    return Position(
        legs=(
            Leg("call", quantity, side, strike, time_to_expiry),
            Leg("put", quantity, side, strike, time_to_expiry),
        ),
        name=f"{side} straddle {strike}",
    )


def strangle(put_strike: float, call_strike: float, time_to_expiry: float,
             side: Side = "long", quantity: float = 1.0) -> Position:
    """An out-of-the-money put and call (put_strike < call_strike), long or short."""
    if put_strike >= call_strike:
        raise ValueError("a strangle needs put_strike < call_strike")
    return Position(
        legs=(
            Leg("put", quantity, side, put_strike, time_to_expiry),
            Leg("call", quantity, side, call_strike, time_to_expiry),
        ),
        name=f"{side} strangle {put_strike}/{call_strike}",
    )


def calendar_spread(option_type: Instrument, strike: float, near_expiry: float,
                    far_expiry: float, quantity: float = 1.0) -> Position:
    """A long calendar: short the near-dated option, long the far-dated option,
    same strike and type. (See the payoff-at-expiry caveat in position.py: a
    calendar's two legs do not expire together.)
    """
    if option_type not in ("call", "put"):
        raise ValueError("a calendar spread is built from calls or puts")
    if not 0 < near_expiry < far_expiry:
        raise ValueError("require 0 < near_expiry < far_expiry")
    return Position(
        legs=(
            Leg(option_type, quantity, "short", strike, near_expiry),
            Leg(option_type, quantity, "long", strike, far_expiry),
        ),
        name=f"{option_type} calendar {strike} ({near_expiry}/{far_expiry})",
    )


def covered_call(call_strike: float, time_to_expiry: float,
                 quantity: float = 1.0) -> Position:
    """Long the underlying and short a call against it (one call per share, given
    the per-share quantity convention in position.py)."""
    return Position(
        legs=(
            Leg("underlying", quantity, "long"),
            Leg("call", quantity, "short", call_strike, time_to_expiry),
        ),
        name=f"covered call {call_strike}",
    )


def iron_condor(put_long_strike: float, put_short_strike: float,
                call_short_strike: float, call_long_strike: float,
                time_to_expiry: float, quantity: float = 1.0) -> Position:
    """Sell an OTM put spread and an OTM call spread (a net-credit, range-bound
    structure). Strikes must be ordered:
        put_long < put_short < call_short < call_long.
    """
    strikes = (put_long_strike, put_short_strike, call_short_strike, call_long_strike)
    if not (strikes[0] < strikes[1] < strikes[2] < strikes[3]):
        raise ValueError(
            "iron condor strikes must satisfy "
            "put_long < put_short < call_short < call_long")
    return Position(
        legs=(
            Leg("put", quantity, "long", put_long_strike, time_to_expiry),
            Leg("put", quantity, "short", put_short_strike, time_to_expiry),
            Leg("call", quantity, "short", call_short_strike, time_to_expiry),
            Leg("call", quantity, "long", call_long_strike, time_to_expiry),
        ),
        name="iron condor "
             f"{put_long_strike}/{put_short_strike}/"
             f"{call_short_strike}/{call_long_strike}",
    )
