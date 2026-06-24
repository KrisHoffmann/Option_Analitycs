"""HTTP routes. Thin: each handler parses a validated request, calls into
pricing/strategies, and serializes the result. No math here (docs/architecture.md).

Domain errors (e.g. an implied-vol request below intrinsic, or invalid leg/grid
combinations) surface as 422 with a clear message rather than a 500.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import (
    ContractRequest,
    GreeksResponse,
    ImpliedVolatilityRequest,
    ImpliedVolatilityResponse,
    PositionRequest,
    PositionResponse,
    PriceResponse,
    SensitivityRequest,
    SensitivityResponse,
    TickersResponse,
)
from data import (
    SUPPORTED_TICKERS,
    ChainFetchError,
    ChainProvider,
    EmptyChainError,
    OptionChain,
    UnsupportedTickerError,
    get_chain_provider,
    get_option_chain,
)
from pricing.black_scholes import price_and_greeks
from pricing.implied_volatility import (
    ImpliedVolatilityError,
    implied_volatility,
)
from pricing.sensitivity import evenly_spaced, sensitivity_series
from strategies.position import (
    Leg,
    Position,
    current_value,
    net_greeks,
    payoff_at_expiry,
)

router = APIRouter()


def _greeks_response(delta, gamma, theta, vega, rho) -> GreeksResponse:
    return GreeksResponse(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


@router.post("/price", response_model=PriceResponse)
def price_contract(request: ContractRequest) -> PriceResponse:
    """Price a single European contract and return its Greeks."""
    try:
        result = price_and_greeks(
            request.option_type, request.spot, request.strike,
            request.time_to_expiry, request.risk_free_rate, request.volatility)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PriceResponse(
        price=result.price,
        greeks=_greeks_response(result.delta, result.gamma, result.theta,
                                result.vega, result.rho),
    )


@router.post("/implied-volatility", response_model=ImpliedVolatilityResponse)
def solve_implied_volatility(
    request: ImpliedVolatilityRequest,
) -> ImpliedVolatilityResponse:
    """Back out the implied volatility for an observed market price."""
    try:
        iv = implied_volatility(
            request.option_type, request.market_price, request.spot,
            request.strike, request.time_to_expiry, request.risk_free_rate)
    except ImpliedVolatilityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ImpliedVolatilityResponse(implied_volatility=iv)


@router.post("/position", response_model=PositionResponse)
def evaluate_position(request: PositionRequest) -> PositionResponse:
    """Payoff-at-expiry and current-value curves plus net Greeks for a position."""
    try:
        legs = tuple(
            Leg(leg.instrument, leg.quantity, leg.side, leg.strike,
                leg.time_to_expiry)
            for leg in request.legs
        )
        position = Position(legs=legs)
        spots = evenly_spaced(request.grid.spot_min, request.grid.spot_max,
                              request.grid.num_points)
        payoff = payoff_at_expiry(position, spots)
        values = current_value(position, spots, request.risk_free_rate,
                               request.volatility)
        net = net_greeks(position, request.spot, request.risk_free_rate,
                         request.volatility)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PositionResponse(
        name=position.name,
        spots=spots,
        payoff_at_expiry=payoff,
        current_value=values,
        net_greeks=_greeks_response(net.delta, net.gamma, net.theta,
                                    net.vega, net.rho),
        net_greeks_spot=request.spot,
    )


@router.post("/sensitivity", response_model=SensitivityResponse)
def greek_sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    """A price/Greek series as one pricing input is swept over a range."""
    contract = request.contract
    try:
        values = evenly_spaced(request.variable_min, request.variable_max,
                               request.num_points)
        series = sensitivity_series(
            contract.option_type, contract.spot, contract.strike,
            contract.time_to_expiry, contract.risk_free_rate,
            contract.volatility,
            variable=request.variable, metric=request.metric,
            variable_values=values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SensitivityResponse(
        variable=request.variable,
        metric=request.metric,
        variable_values=values,
        metric_values=series,
    )


@router.get("/tickers", response_model=TickersResponse)
def supported_tickers() -> TickersResponse:
    """The underlyings for which a chain can be fetched."""
    return TickersResponse(tickers=list(SUPPORTED_TICKERS))


@router.get("/chain/{ticker}", response_model=OptionChain)
def option_chain(
    ticker: str,
    provider: ChainProvider = Depends(get_chain_provider),
) -> OptionChain:
    """Fetch the live options chain for a supported ticker.

    Distinguishes client error (unsupported ticker -> 404) from upstream data
    failure (empty/stale -> 502, fetch failure -> 502) so the cause is clear.
    """
    try:
        return get_option_chain(ticker, provider=provider)
    except UnsupportedTickerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmptyChainError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ChainFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
