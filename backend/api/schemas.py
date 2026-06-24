"""Request/response models for the API, defined once (docs/architecture.md).

These Pydantic models are the single definition of the wire contract; the
frontend's TypeScript types in ``frontend/lib`` mirror them. Validation lives
here (field bounds, enums), so the route handlers stay free of input checking
and of math.

Units follow pricing.black_scholes: rates and vols are decimals, time is in
years.
"""

from __future__ import annotations

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
        "spot", "strike", "time_to_expiry", "risk_free_rate", "volatility"
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
