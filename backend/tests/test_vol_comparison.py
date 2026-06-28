"""Tests for the implied-vs-realized comparison (V2-B).

Two things are checked deliberately, because they are where the feature would
mislead if wrong:

  - the ATM-forward IV interpolation to k = 0, and
  - the forward/backward alignment: realized is a backward *series* lined up to
    the price-history dates, while implied is a single *forward* observation from
    today's chain (there is no historical implied series, by construction).

No network: the chain and price history are synthetic, and the route is exercised
with a fake provider injected via FastAPI's dependency override.
"""

import math
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from data import get_chain_provider
from data.chain import (
    ExpiryChain,
    OptionChain,
    OptionQuote,
    PriceHistory,
    PricePoint,
)
from data.provider import ChainFetchError
from pricing.black_scholes import price as bsm_price
from pricing.vol_comparison import (
    VOL_PREMIUM_NOTE,
    RealizedVolPoint,
    _interpolate_atm_iv,
    build_vol_comparison,
)
from pricing.vol_surface import ExpirySlice, FilterCounts, SurfacePoint

NOW = datetime(2026, 6, 28, tzinfo=UTC)
R = 0.043
Q = 0.0


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------
def _point(k: float, iv: float) -> SurfacePoint:
    return SurfacePoint(option_type="call", strike=100.0, log_moneyness=k,
                        time_to_expiry=30 / 365, implied_volatility=iv,
                        mid_price=1.0, open_interest=1000, relative_spread=0.02)


def _slice(points: list[SurfacePoint], days: int = 30) -> ExpirySlice:
    return ExpirySlice(
        expiry=date(2026, 7, 28), time_to_expiry=days / 365, forward=100.0,
        points=tuple(sorted(points, key=lambda p: p.log_moneyness)),
        filtered=FilterCounts(len(points), len(points), 0, 0, 0, 0, 0))


def _quote(option_type: str, strike: float, spot: float, sigma: float,
           days: int) -> OptionQuote:
    """An OTM quote priced by our own BSM at `sigma`, so the solver recovers it."""
    mid = bsm_price(option_type, spot, strike, days / 365, R, sigma, Q)
    return OptionQuote(
        contract_symbol=f"X{strike}{option_type}", option_type=option_type,
        strike=strike, bid=mid * 0.99, ask=mid * 1.01, open_interest=1000,
        last_trade_date=None)


def _chain_with_atm(spot: float, sigma: float, days: int = 30,
                    ticker: str = "AAPL") -> OptionChain:
    """A chain with one near-dated expiry whose OTM put and call bracket the
    forward, both priced at `sigma` (so the ATM-forward IV must come back ~sigma).

    Quotes are priced at q = 0; tests that invert through the route (which applies
    each ticker's assumed q) use a zero-q ticker so the recovered IV stays clean.
    """
    expiry = NOW.date() + timedelta(days=days)
    calls = [_quote("call", spot + 1, spot, sigma, days)]
    puts = [_quote("put", spot - 1, spot, sigma, days)]
    return OptionChain(
        ticker=ticker, spot=spot, fetched_at=NOW,
        expiries=[ExpiryChain(expiry=expiry, time_to_expiry=days / 365,
                              calls=calls, puts=puts)])


def _alternating_history(a: float, n_returns: int,
                         ticker: str = "AAPL") -> PriceHistory:
    closes = [100.0]
    for i in range(n_returns):
        closes.append(closes[-1] * math.exp(a if i % 2 == 0 else -a))
    start = NOW.date() - timedelta(days=len(closes) - 1)
    points = [PricePoint(date=start + timedelta(days=i), close=c)
              for i, c in enumerate(closes)]
    return PriceHistory(ticker=ticker, fetched_at=NOW, points=points)


# ---------------------------------------------------------------------------
# ATM-forward interpolation
# ---------------------------------------------------------------------------
def test_interpolate_atm_iv_brackets_zero():
    # Points straddling k = 0 are linearly interpolated in k to the forward.
    s = _slice([_point(-0.05, 0.20), _point(0.15, 0.40)])
    iv, method = _interpolate_atm_iv(s)
    # weight = (0 - (-0.05)) / (0.15 - (-0.05)) = 0.25 -> 0.20 + 0.25*0.20 = 0.25
    assert iv == pytest.approx(0.25)
    assert method == "interpolated"


def test_interpolate_atm_iv_symmetric_is_midpoint():
    s = _slice([_point(-0.1, 0.20), _point(0.1, 0.30)])
    iv, method = _interpolate_atm_iv(s)
    assert iv == pytest.approx(0.25)
    assert method == "interpolated"


def test_interpolate_atm_iv_one_sided_falls_back_to_nearest():
    # Only the call wing survived: no bracket, so take the IV nearest the forward.
    s = _slice([_point(0.05, 0.22), _point(0.20, 0.35)])
    iv, method = _interpolate_atm_iv(s)
    assert iv == pytest.approx(0.22)
    assert method == "nearest-strike"


# ---------------------------------------------------------------------------
# End-to-end build
# ---------------------------------------------------------------------------
def test_build_recovers_atm_iv_and_forms_same_date_premium():
    sigma = 0.25
    a, window = 0.01, 20
    chain = _chain_with_atm(spot=100.0, sigma=sigma)
    history = _alternating_history(a, n_returns=40)

    result = build_vol_comparison(chain, history, R, Q, realized_window=window)

    # Implied: our solver recovers the input sigma at ATM-forward.
    assert result.implied_atm_vol == pytest.approx(sigma, abs=1e-4)
    assert result.atm_method == "interpolated"
    assert result.implied_days_to_expiry == 30

    # Realized: alternating +-a over an even window -> a*sqrt(W/(W-1)), annualized.
    expected_realized = a * math.sqrt(window / (window - 1)) * math.sqrt(252)
    assert result.latest_realized_vol == pytest.approx(expected_realized)

    # Premium is exactly the same-date spread, and the framing travels with it.
    assert result.vol_premium == pytest.approx(
        result.implied_atm_vol - result.latest_realized_vol)
    assert result.vol_premium_note == VOL_PREMIUM_NOTE


def test_alignment_realized_is_backward_series_implied_is_single_forward():
    a, window = 0.01, 20
    chain = _chain_with_atm(spot=100.0, sigma=0.25)
    history = _alternating_history(a, n_returns=40)  # 41 closes

    result = build_vol_comparison(chain, history, R, Q, realized_window=window)

    # Backward leg: a series, one fewer than (closes - warmup), ending on the most
    # recent close's date -- it is aligned to history, not to the option.
    assert len(result.realized) == len(history.points) - window
    assert result.realized[-1].date == history.points[-1].date
    assert all(isinstance(p, RealizedVolPoint) for p in result.realized)

    # Forward leg: a single observation tied to the option expiry, NOT a series.
    assert result.implied_expiry == chain.expiries[0].expiry
    assert result.implied_time_to_expiry == pytest.approx(30 / 365)


def test_build_picks_expiry_nearest_target_days():
    # Two expiries; the comparison must read implied vol from the ~30d one.
    spot, sigma = 100.0, 0.25
    near = ExpiryChain(
        expiry=NOW.date() + timedelta(days=28), time_to_expiry=28 / 365,
        calls=[_quote("call", spot + 1, spot, sigma, 28)],
        puts=[_quote("put", spot - 1, spot, sigma, 28)])
    far = ExpiryChain(
        expiry=NOW.date() + timedelta(days=180), time_to_expiry=180 / 365,
        calls=[_quote("call", spot + 1, spot, 0.40, 180)],
        puts=[_quote("put", spot - 1, spot, 0.40, 180)])
    chain = OptionChain(ticker="AAPL", spot=spot, fetched_at=NOW,
                        expiries=[near, far])
    history = _alternating_history(0.01, n_returns=40)

    result = build_vol_comparison(chain, history, R, Q, realized_window=20)
    assert result.implied_days_to_expiry == 28
    assert result.implied_atm_vol == pytest.approx(sigma, abs=1e-4)


def test_build_with_no_usable_chain_yields_no_implied_but_keeps_realized():
    # Every quote lacks a two-sided market -> surface slice is empty -> no ATM
    # read. Realized still computes; the premium is simply undefined.
    expiry = NOW.date() + timedelta(days=30)
    dead = OptionQuote(contract_symbol="X", option_type="call", strike=101.0,
                       bid=None, ask=None, open_interest=1000)
    chain = OptionChain(
        ticker="AAPL", spot=100.0, fetched_at=NOW,
        expiries=[ExpiryChain(expiry=expiry, time_to_expiry=30 / 365,
                              calls=[dead], puts=[])])
    history = _alternating_history(0.01, n_returns=40)

    result = build_vol_comparison(chain, history, R, Q, realized_window=20)
    assert result.implied_atm_vol is None
    assert result.vol_premium is None
    assert result.realized  # realized series is unaffected
    assert result.latest_realized_vol is not None


# ---------------------------------------------------------------------------
# Route (dependency-injected fake provider, no network)
# ---------------------------------------------------------------------------
class _FakeDataProvider:
    def __init__(self, chain=None, history=None,
                 chain_error=None, history_error=None):
        self._chain = chain
        self._history = history
        self._chain_error = chain_error
        self._history_error = history_error

    def get_option_chain(self, ticker: str) -> OptionChain:
        if self._chain_error is not None:
            raise self._chain_error
        return self._chain

    def get_price_history(self, ticker: str,
                          lookback_days: int = 365) -> PriceHistory:
        if self._history_error is not None:
            raise self._history_error
        return self._history


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_vol_comparison_endpoint_returns_series_and_framed_premium(client):
    # AMZN has assumed q = 0, matching the q=0 pricing of the synthetic quotes, so
    # the route's solver recovers the input sigma cleanly through the full path.
    chain = _chain_with_atm(spot=100.0, sigma=0.25, ticker="AMZN")
    history = _alternating_history(0.01, n_returns=40, ticker="AMZN")
    app.dependency_overrides[get_chain_provider] = lambda: _FakeDataProvider(
        chain=chain, history=history)

    resp = client.get("/vol-comparison/AMZN")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AMZN"
    assert body["implied_atm_vol"] == pytest.approx(0.25, abs=1e-4)
    assert body["realized"]  # backward series present
    assert body["realized"][-1]["date"] == history.points[-1].date.isoformat()
    assert body["vol_premium"] is not None
    # The mandatory framing ships in the payload (so the chart can render it).
    assert body["vol_premium_note"] == VOL_PREMIUM_NOTE


def test_vol_comparison_endpoint_unsupported_ticker_is_404(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeDataProvider(
        chain=_chain_with_atm(100.0, 0.25),
        history=_alternating_history(0.01, 40))
    assert client.get("/vol-comparison/DOGE").status_code == 404


def test_vol_comparison_endpoint_fetch_failure_is_502(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeDataProvider(
        chain=_chain_with_atm(100.0, 0.25),
        history_error=ChainFetchError("source unavailable"))
    assert client.get("/vol-comparison/AAPL").status_code == 502
