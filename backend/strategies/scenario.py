"""Scenario / risk matrix: how a position's model value changes under an
instantaneous shock to spot and volatility.

Pure math built on the position model (``strategies.position``) and, through it,
``pricing.black_scholes``. No I/O, no globals, no FastAPI imports
(docs/architecture.md) -- the route parses the request and serializes the
result, this module only reprices.

What it computes, and the decisions stated where they apply:

  - **Mark-to-market model value under a shock, not P&L.** Each cell is the
    position's current (pre-expiry) model value when the spot and the flat
    volatility are shocked away from today's. The change-from-base is reported as
    a "change in model value", never as profit/loss -- a mark-to-market value
    change is legitimate risk analysis; calling it P&L would imply a realized
    trade (CLAUDE.md positioning).

  - **Instantaneous shock.** Each leg's ``time_to_expiry`` is held fixed; only
    spot and vol move. This is the standard risk matrix ("if the market gapped
    right now"). Rolling time forward (theta decay) is a deliberate, separate
    extension, not mixed in here.

  - **Spot shock is multiplicative (%), vol shock is additive (pp).** A +10%
    spot shock means S -> S*1.10; a +5 pp vol shock means sigma -> sigma + 0.05
    (percentage *points* of volatility, the standard risk convention). A shocked
    vol is clamped at 0 (BSM handles sigma = 0 as discounted intrinsic).

  - **One flat vol, shocked uniformly across all legs.** Consistent with the
    position model's single-flat-vol assumption; per-strike/expiry vol is a
    vol-surface concern, out of scope here. r and q are held constant.

  - **Base value is today's value at (0% spot, 0 pp vol)**, computed exactly
    rather than read off the grid, so the change surface is always measured from
    the true current value even if the grid does not land on 0/0. ``base_row`` /
    ``base_col`` mark the grid cell nearest (0, 0) for highlighting.

Units follow ``pricing.black_scholes``: rates/vols are decimals, time is years.
"""

from __future__ import annotations

from dataclasses import dataclass

from pricing.sensitivity import evenly_spaced
from strategies.position import Position, current_value

# Defaults: spot -30%..+30% (13 columns, 5% steps), vol -10pp..+10pp (9 rows,
# 2.5pp steps). Both ranges straddle 0 so the base cell sits on the grid.
DEFAULT_SPOT_SHOCK_MIN_PCT = -30.0
DEFAULT_SPOT_SHOCK_MAX_PCT = 30.0
DEFAULT_SPOT_STEPS = 13
DEFAULT_VOL_SHOCK_MIN_PP = -10.0
DEFAULT_VOL_SHOCK_MAX_PP = 10.0
DEFAULT_VOL_STEPS = 9


@dataclass(frozen=True)
class ScenarioMatrix:
    """A 2D grid of position model values under spot/vol shocks.

    ``values`` and ``changes`` are indexed [row][col] = [vol shock][spot shock].
    ``changes[r][c] = values[r][c] - base_value``. ``base_value`` is the value at
    no shock (0% spot, 0 pp vol).
    """

    spot_shocks_pct: tuple[float, ...]   # columns, multiplicative % of spot
    vol_shocks_pp: tuple[float, ...]     # rows, additive percentage points of vol
    spot: float
    base_volatility: float
    risk_free_rate: float
    dividend_yield: float
    base_value: float
    base_row: int                        # vol-shock index nearest 0 pp
    base_col: int                        # spot-shock index nearest 0 %
    values: tuple[tuple[float, ...], ...]
    changes: tuple[tuple[float, ...], ...]


def _nearest_zero_index(values: tuple[float, ...]) -> int:
    """Index of the value closest to zero (for highlighting the base cell)."""
    return min(range(len(values)), key=lambda i: abs(values[i]))


def build_scenario_matrix(
    position: Position,
    spot: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
    *,
    spot_shock_min_pct: float = DEFAULT_SPOT_SHOCK_MIN_PCT,
    spot_shock_max_pct: float = DEFAULT_SPOT_SHOCK_MAX_PCT,
    spot_steps: int = DEFAULT_SPOT_STEPS,
    vol_shock_min_pp: float = DEFAULT_VOL_SHOCK_MIN_PP,
    vol_shock_max_pp: float = DEFAULT_VOL_SHOCK_MAX_PP,
    vol_steps: int = DEFAULT_VOL_STEPS,
) -> ScenarioMatrix:
    """Reprice a position across a grid of spot and vol shocks (pure, no I/O).

    Args:
        position: the multi-leg position to reprice.
        spot: current underlying price S, > 0.
        risk_free_rate: r, annual continuously-compounded, decimal.
        volatility: the base flat volatility sigma, decimal, >= 0.
        dividend_yield: q, continuous dividend yield, decimal.
        spot_shock_min_pct, spot_shock_max_pct, spot_steps: spot-shock axis, as
            multiplicative percentages of spot (e.g. -30 .. +30 over 13 columns).
        vol_shock_min_pp, vol_shock_max_pp, vol_steps: vol-shock axis, as additive
            percentage points of volatility (e.g. -10 .. +10 over 9 rows).

    Returns:
        A ScenarioMatrix: the two shock axes, the value grid [row=vol][col=spot],
        the change-from-base grid, the base value, and the base cell indices.

    Raises:
        ValueError: on a degenerate grid (fewer than 2 steps, or min >= max).
    """
    if spot_steps < 2 or vol_steps < 2:
        raise ValueError("spot_steps and vol_steps must each be >= 2")
    if spot_shock_min_pct >= spot_shock_max_pct:
        raise ValueError("spot_shock_min_pct must be < spot_shock_max_pct")
    if vol_shock_min_pp >= vol_shock_max_pp:
        raise ValueError("vol_shock_min_pp must be < vol_shock_max_pp")

    spot_shocks = tuple(
        evenly_spaced(spot_shock_min_pct, spot_shock_max_pct, spot_steps))
    vol_shocks = tuple(
        evenly_spaced(vol_shock_min_pp, vol_shock_max_pp, vol_steps))

    # Base value at no shock, computed exactly (not read off the grid) so the
    # change surface is measured from the true current value.
    base_value = current_value(
        position, [spot], risk_free_rate, volatility, dividend_yield)[0]

    values: list[tuple[float, ...]] = []
    changes: list[tuple[float, ...]] = []
    for vol_pp in vol_shocks:
        shocked_vol = max(0.0, volatility + vol_pp / 100.0)
        shocked_spots = [spot * (1.0 + pct / 100.0) for pct in spot_shocks]
        row = current_value(
            position, shocked_spots, risk_free_rate, shocked_vol, dividend_yield)
        values.append(tuple(row))
        changes.append(tuple(v - base_value for v in row))

    return ScenarioMatrix(
        spot_shocks_pct=spot_shocks,
        vol_shocks_pp=vol_shocks,
        spot=spot,
        base_volatility=volatility,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        base_value=base_value,
        base_row=_nearest_zero_index(vol_shocks),
        base_col=_nearest_zero_index(spot_shocks),
        values=tuple(values),
        changes=tuple(changes),
    )
