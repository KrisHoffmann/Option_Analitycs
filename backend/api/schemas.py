"""Request/response models for the API, defined once (docs/architecture.md).

These Pydantic models are the single definition of the wire contract; the
frontend's TypeScript types in ``frontend/lib`` mirror them. Validation lives
here (field bounds, enums), so the route handlers stay free of input checking
and of math.

Units follow pricing.black_scholes: rates and vols are decimals, time is in
years.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

OptionTypeField = Literal["call", "put"]
InstrumentField = Literal["call", "put", "underlying"]
SideField = Literal["long", "short"]


# --------------------------------------------------------------------------
# Contract pricing
# --------------------------------------------------------------------------
class ContractRequest(BaseModel):
    option_type: OptionTypeField
    spot: float = Field(gt=0, description="Underlying price S")
    strike: float = Field(gt=0, description="Strike K")
    time_to_expiry: float = Field(ge=0, description="Years to expiry T")
    risk_free_rate: float = Field(description="Annual cont.-comp. rate r (decimal)")
    volatility: float = Field(ge=0, description="Annualized volatility sigma (decimal)")
    dividend_yield: float = Field(default=0.0, description="Continuous yield q (dec.)")


class GreeksResponse(BaseModel):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


class PriceResponse(BaseModel):
    price: float
    greeks: GreeksResponse


# --------------------------------------------------------------------------
# BSM vs binomial (CRR) comparison
# --------------------------------------------------------------------------
class PriceComparisonRequest(BaseModel):
    contract: ContractRequest
    steps: int = Field(default=100, ge=10, le=2000,
                       description="CRR tree steps (accuracy vs. speed)")


class PriceComparisonResponse(BaseModel):
    bsm_price: float
    greeks: GreeksResponse
    crr_european: float
    crr_american: float
    early_exercise_premium: float  # crr_american - crr_european
    steps: int


# --------------------------------------------------------------------------
# Implied volatility
# --------------------------------------------------------------------------
class ImpliedVolatilityRequest(BaseModel):
    option_type: OptionTypeField
    market_price: float = Field(gt=0, description="Observed option price to match")
    spot: float = Field(gt=0)
    strike: float = Field(gt=0)
    time_to_expiry: float = Field(gt=0)
    risk_free_rate: float = Field(default=0.0)


class ImpliedVolatilityResponse(BaseModel):
    implied_volatility: float


# --------------------------------------------------------------------------
# Positions: payoff, current value, net Greeks
# --------------------------------------------------------------------------
class LegSchema(BaseModel):
    instrument: InstrumentField
    quantity: float = Field(gt=0)
    side: SideField
    strike: float | None = Field(default=None, gt=0)
    time_to_expiry: float | None = Field(default=None, ge=0)


class SpotGridSpec(BaseModel):
    """Server builds an evenly-spaced spot grid from this (keeps payloads small)."""

    spot_min: float = Field(gt=0)
    spot_max: float = Field(gt=0)
    num_points: int = Field(default=101, ge=2, le=2000)


class PositionRequest(BaseModel):
    legs: list[LegSchema] = Field(min_length=1)
    grid: SpotGridSpec
    spot: float = Field(gt=0, description="Current underlying; net Greeks here")
    risk_free_rate: float = Field(default=0.0)
    volatility: float = Field(ge=0, description="Flat volatility for current-value")
    dividend_yield: float = Field(default=0.0, description="Continuous yield q (dec.)")


class PositionResponse(BaseModel):
    name: str
    spots: list[float]
    payoff_at_expiry: list[float]
    current_value: list[float]
    net_greeks: GreeksResponse
    net_greeks_spot: float = Field(description="Spot at which net_greeks was evaluated")


# --------------------------------------------------------------------------
# Greek-sensitivity series
# --------------------------------------------------------------------------
class SensitivityRequest(BaseModel):
    contract: ContractRequest
    variable: Literal[
        "spot", "strike", "time_to_expiry", "risk_free_rate", "volatility",
        "dividend_yield",
    ]
    metric: Literal["price", "delta", "gamma", "theta", "vega", "rho"]
    variable_min: float
    variable_max: float
    num_points: int = Field(default=101, ge=2, le=2000)


class SensitivityResponse(BaseModel):
    variable: str
    metric: str
    variable_values: list[float]
    metric_values: list[float]


# --------------------------------------------------------------------------
# Data / chain
# --------------------------------------------------------------------------
# The chain response itself is data.chain.OptionChain (defined once in the data
# layer and serialized directly).
class TickersResponse(BaseModel):
    tickers: list[str]


# --------------------------------------------------------------------------
# Volatility surface (V2-A)
# --------------------------------------------------------------------------
# Mirrors pricing.vol_surface dataclasses; the route maps the pure result onto
# these for serialization (the pricing layer stays pydantic-free, like
# BlackScholesResult).
class SurfacePointResponse(BaseModel):
    option_type: OptionTypeField
    strike: float
    log_moneyness: float = Field(description="k = ln(K / F), forward moneyness")
    time_to_expiry: float
    implied_volatility: float = Field(description="BSM IV (decimal) from our solver")
    mid_price: float = Field(description="(bid + ask) / 2, the price inverted")
    open_interest: int
    relative_spread: float


class FilterCountsResponse(BaseModel):
    """How many OTM candidates were dropped, and why -- the data-quality audit."""

    candidates: int
    retained: int
    no_two_sided_quote: int
    spread_too_wide: int
    insufficient_open_interest: int
    stale_quote: int
    solver_failed: int


class ExpirySliceResponse(BaseModel):
    expiry: date
    time_to_expiry: float
    forward: float = Field(description="F = S*e^((r-q)T)")
    points: list[SurfacePointResponse]
    filtered: FilterCountsResponse


class VolSurfaceResponse(BaseModel):
    ticker: str
    spot: float
    fetched_at: datetime
    risk_free_rate: float = Field(description="Assumed r (decimal), a constant")
    dividend_yield: float = Field(description="Assumed q (decimal), per ticker")
    slices: list[ExpirySliceResponse]


# --------------------------------------------------------------------------
# Implied vs realized volatility (V2-B)
# --------------------------------------------------------------------------
# Mirrors pricing.vol_comparison. The asymmetry is intentional: `realized` is a
# full backward-looking series; the implied_* fields are a single forward-looking
# observation (today's near-dated ATM-forward IV). There is no historical implied
# series -- a free source gives no option-quote history and v1 stores none -- so
# we never fabricate one. `vol_premium` is the same-date spread, and
# `vol_premium_note` is the mandatory framing that ships with it (shown on the
# chart, not just the README).
class RealizedVolPointResponse(BaseModel):
    date: date
    realized_vol: float = Field(description="Annualized realized vol (decimal)")


class VolComparisonResponse(BaseModel):
    ticker: str
    spot: float
    fetched_at: datetime
    risk_free_rate: float = Field(description="Assumed r (decimal), a constant")
    dividend_yield: float = Field(description="Assumed q (decimal), per ticker")

    realized_window_trading_days: int = Field(
        description="Trailing window for realized vol (trading days)")
    trading_days_per_year: int = Field(
        description="Annualization factor's argument (252)")
    realized: list[RealizedVolPointResponse] = Field(
        description="Backward-looking realized-vol series, chronological")
    latest_realized_vol: float | None = Field(
        description="Most recent realized vol, the premium's backward leg")

    implied_atm_vol: float | None = Field(
        description="Forward-looking ATM-forward IV from our solver (decimal)")
    implied_expiry: date | None = None
    implied_days_to_expiry: int | None = Field(
        default=None, description="Actual day count of the near-dated expiry used")
    implied_time_to_expiry: float | None = None
    forward: float | None = Field(default=None, description="F = S*e^((r-q)T)")
    atm_method: str | None = Field(
        default=None, description="'interpolated' or 'nearest-strike'")

    vol_premium: float | None = Field(
        description="Same-date spread: implied_atm_vol - latest_realized_vol")
    vol_premium_note: str = Field(
        description="Mandatory framing for the premium; render it on the chart")
