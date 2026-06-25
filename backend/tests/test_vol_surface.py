"""Tests for the V2-A volatility surface.

Offline and deterministic, the way the data caveats demand (docs/architecture.md):
the pure builder is exercised against synthetic chains, and the route through a
fake provider injected via FastAPI's dependency override. No live yfinance, no
snapshot tests.

Coverage:
  - correct grid: forward log-moneyness and recovered IV,
  - each quote filter exercised on a crafted bad quote (right drop bucket),
  - explicit gaps (filtered strikes are absent, never interpolated),
  - the expiry window bounds both ends,
  - a synthetic smile recovers higher IV in the OTM-put wing (skew),
  - a wing-coverage acceptance test: the tuned filters leave a legible smile,
  - the route returns 200 / 404 / 502 as the chain endpoint does.
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from data import EmptyChainError, get_chain_provider
from data.chain import ExpiryChain, OptionChain, OptionQuote
from pricing.black_scholes import price
from pricing.vol_surface import build_vol_surface

NOW = datetime(2026, 6, 24, tzinfo=UTC)
R = 0.043   # match the route's RISK_FREE_RATE so synthetic IVs round-trip
Q = 0.012   # SPY-like dividend yield


# ---------------------------------------------------------------------------
# Synthetic chain helpers (no network)
# ---------------------------------------------------------------------------
def _quote(option_type, strike, mid, *, rel_spread=0.04, oi=500, last_trade=NOW):
    half = mid * rel_spread / 2.0
    return OptionQuote(
        contract_symbol=f"X{int(strike)}{option_type[0].upper()}",
        option_type=option_type, strike=float(strike),
        bid=mid - half, ask=mid + half, open_interest=oi,
        last_trade_date=last_trade,
    )


def _priced_quote(option_type, strike, spot, t, vol, **kw):
    mid = price(option_type, spot, strike, t, R, vol, Q)
    return _quote(option_type, strike, mid, **kw)


def _smile_vol(strike, spot):
    """Downward skew: OTM puts (low strikes) richer than OTM calls."""
    moneyness = (spot - strike) / spot
    return 0.20 + (0.6 * moneyness if strike < spot else -0.1 * moneyness)


def _chain(spot, days, strikes, vol_fn, *, ticker="SPY", **qkw):
    t = days / 365.0
    calls = [_priced_quote("call", k, spot, t, vol_fn(k, spot), **qkw) for k in strikes]
    puts = [_priced_quote("put", k, spot, t, vol_fn(k, spot), **qkw) for k in strikes]
    return OptionChain(
        ticker=ticker, spot=spot, fetched_at=NOW,
        expiries=[ExpiryChain(expiry=NOW.date() + timedelta(days=days),
                              time_to_expiry=t, calls=calls, puts=puts)])


def _one_expiry_chain(calls, puts, *, spot=100.0, days=30, ticker="SPY"):
    return OptionChain(
        ticker=ticker, spot=spot, fetched_at=NOW,
        expiries=[ExpiryChain(expiry=NOW.date() + timedelta(days=days),
                              time_to_expiry=days / 365.0,
                              calls=calls, puts=puts)])


# ---------------------------------------------------------------------------
# Correct grid: forward log-moneyness + recovered IV
# ---------------------------------------------------------------------------
def test_grid_recovers_flat_iv_and_forward_log_moneyness():
    chain = _chain(100.0, 30, [90, 95, 100, 105, 110], lambda k, s: 0.25)
    surface = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q)

    assert len(surface.slices) == 1
    sl = surface.slices[0]
    # OTM only: puts 90/95, calls 100/105/110 -> 5 candidates, all retained.
    assert sl.filtered.candidates == 5
    assert sl.filtered.retained == 5

    forward = 100.0 * math.exp((R - Q) * sl.time_to_expiry)
    assert sl.forward == pytest.approx(forward)
    for point in sl.points:
        assert point.implied_volatility == pytest.approx(0.25, abs=1e-4)
        assert point.log_moneyness == pytest.approx(math.log(point.strike / forward))
    # Points are sorted ascending in log-moneyness (left-to-right on a heatmap).
    ks = [p.log_moneyness for p in sl.points]
    assert ks == sorted(ks)


def test_only_otm_side_is_used():
    chain = _chain(100.0, 30, [90, 110], lambda k, s: 0.25)
    sl = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q).slices[0]
    sides = {(p.option_type, p.strike) for p in sl.points}
    assert sides == {("put", 90.0), ("call", 110.0)}  # OTM put below, OTM call above


# ---------------------------------------------------------------------------
# Each filter exercised on a crafted bad quote -> the right drop bucket
# ---------------------------------------------------------------------------
def test_filter_no_two_sided_quote():
    bad = _quote("put", 90, 2.0)
    bad = bad.model_copy(update={"bid": None})  # no real two-sided market
    sl = build_vol_surface(_one_expiry_chain([], [bad]),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.candidates == 1
    assert sl.filtered.no_two_sided_quote == 1
    assert sl.filtered.retained == 0
    assert sl.points == ()


def test_filter_spread_too_wide():
    bad = _quote("put", 90, 1.5, rel_spread=0.667)  # (ask-bid)/mid ~0.67 > 0.25
    sl = build_vol_surface(_one_expiry_chain([], [bad]),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.spread_too_wide == 1
    assert sl.filtered.retained == 0


def test_filter_insufficient_open_interest():
    bad = _priced_quote("put", 90, 100.0, 30 / 365.0, 0.25, oi=5)  # < 10
    sl = build_vol_surface(_one_expiry_chain([], [bad]),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.insufficient_open_interest == 1
    assert sl.filtered.retained == 0


def test_filter_stale_quote():
    bad = _priced_quote("put", 90, 100.0, 30 / 365.0, 0.25,
                        last_trade=NOW - timedelta(days=30))  # > 10 day cutoff
    sl = build_vol_surface(_one_expiry_chain([], [bad]),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.stale_quote == 1
    assert sl.filtered.retained == 0


def test_missing_trade_date_is_not_treated_as_stale():
    good = _priced_quote("put", 90, 100.0, 30 / 365.0, 0.25,
                         last_trade=None)  # provider omitted it
    sl = build_vol_surface(_one_expiry_chain([], [good]),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.stale_quote == 0
    assert sl.filtered.retained == 1


def test_filter_solver_failure_is_a_gap():
    # An OTM call quoted above the no-arbitrage upper bound (mid > S) has no IV.
    bad = _quote("call", 110, 125.0)  # mid 125 > spot 100
    sl = build_vol_surface(_one_expiry_chain([bad], []),
                           risk_free_rate=R, dividend_yield=Q).slices[0]
    assert sl.filtered.solver_failed == 1
    assert sl.filtered.retained == 0


def test_filtered_strikes_are_explicit_gaps_not_interpolated():
    # One thin-OI strike sits between liquid ones; it must simply be absent.
    good_low = _priced_quote("put", 90, 100.0, 30 / 365.0, 0.25)
    thin_mid = _priced_quote("put", 95, 100.0, 30 / 365.0, 0.25, oi=1)
    chain = _one_expiry_chain([], [good_low, thin_mid])
    sl = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q).slices[0]
    strikes = {p.strike for p in sl.points}
    assert strikes == {90.0}  # 95 is a gap, not interpolated in
    assert sl.filtered.candidates == 2
    assert sl.filtered.retained == 1


# ---------------------------------------------------------------------------
# Expiry window bounds both ends
# ---------------------------------------------------------------------------
def test_expiry_window_excludes_near_and_far():
    spot = 100.0
    expiries = []
    for days in (1, 30, 400):  # too near, in-window, too far
        t = days / 365.0
        expiries.append(ExpiryChain(
            expiry=NOW.date() + timedelta(days=days), time_to_expiry=t,
            calls=[_priced_quote("call", 110, spot, t, 0.25)],
            puts=[_priced_quote("put", 90, spot, t, 0.25)]))
    chain = OptionChain(ticker="SPY", spot=spot, fetched_at=NOW, expiries=expiries)
    surface = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q)
    kept_days = {round(s.time_to_expiry * 365.0) for s in surface.slices}
    assert kept_days == {30}


# ---------------------------------------------------------------------------
# Smile: higher IV in the OTM-put wing (skew)
# ---------------------------------------------------------------------------
def test_synthetic_smile_recovers_higher_iv_in_otm_put_wing():
    chain = _chain(100.0, 37, [80, 90, 100, 110, 120], _smile_vol)
    sl = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q).slices[0]
    # Points are sorted by log-moneyness: first = deepest OTM put, last = OTM call.
    otm_put = sl.points[0]
    otm_call = sl.points[-1]
    assert otm_put.option_type == "put"
    assert otm_put.log_moneyness < 0 < otm_call.log_moneyness
    assert otm_put.implied_volatility > otm_call.implied_volatility
    # And it recovers the smile vol that priced it (K=80 -> 0.20 + 0.6*0.2 = 0.32).
    assert otm_put.implied_volatility == pytest.approx(0.32, abs=1e-2)


# ---------------------------------------------------------------------------
# Wing-coverage acceptance test (the explicit guard from the design revision):
# on an SPY-like near-term expiry the tuned filters must leave a legible smile.
#
# Numbers justified: a $500 underlying with $5 strikes over [400, 600] is ~+/-20%
# in strike; we require the retained cloud to (a) keep >= 15 points and (b) span
# at least +/-15% forward log-moneyness on BOTH wings -- enough to read a smile.
# ---------------------------------------------------------------------------
def test_wing_coverage_leaves_a_legible_smile():
    spot = 500.0
    strikes = list(range(400, 605, 5))  # 41 strikes, +/-20%
    # Realistic: wings carry wider (but still acceptable) spreads and thinner OI.
    def qkw_for(strike):
        far = abs(strike - spot) / spot
        return {"rel_spread": 0.05 + 0.5 * far, "oi": 500 if far < 0.1 else 80}

    t = 29 / 365.0
    calls = [_priced_quote("call", k, spot, t, _smile_vol(k, spot), **qkw_for(k))
             for k in strikes]
    puts = [_priced_quote("put", k, spot, t, _smile_vol(k, spot), **qkw_for(k))
            for k in strikes]
    expiry = ExpiryChain(expiry=NOW.date() + timedelta(days=29),
                         time_to_expiry=t, calls=calls, puts=puts)
    chain = OptionChain(ticker="SPY", spot=spot, fetched_at=NOW, expiries=[expiry])

    sl = build_vol_surface(chain, risk_free_rate=R, dividend_yield=Q).slices[0]
    ks = [p.log_moneyness for p in sl.points]
    assert sl.filtered.retained >= 15
    assert min(ks) <= -0.15   # OTM-put wing reaches at least -15% forward-moneyness
    assert max(ks) >= 0.15    # OTM-call wing reaches at least +15%


# ---------------------------------------------------------------------------
# Route (dependency-injected fake provider)
# ---------------------------------------------------------------------------
class _FakeProvider:
    def __init__(self, chain=None, error=None):
        self._chain = chain
        self._error = error

    def get_option_chain(self, ticker: str) -> OptionChain:
        if self._error is not None:
            raise self._error
        return self._chain


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_vol_surface_endpoint_returns_serialized_surface(client):
    chain = _chain(500.0, 30, [450, 475, 500, 525, 550], _smile_vol)
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(chain=chain)
    resp = client.get("/vol-surface/SPY")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "SPY"
    assert body["risk_free_rate"] == pytest.approx(R)
    assert body["dividend_yield"] == pytest.approx(Q)  # sourced per ticker
    assert len(body["slices"]) == 1
    sl = body["slices"][0]
    assert sl["points"], "expected a non-empty IV cloud"
    point_keys = sl["points"][0].keys()
    assert {"log_moneyness", "implied_volatility", "option_type"} <= point_keys
    assert "retained" in sl["filtered"]


def test_vol_surface_endpoint_unsupported_ticker_is_404(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(
        chain=_chain(100.0, 30, [90, 110], lambda k, s: 0.25))
    assert client.get("/vol-surface/DOGE").status_code == 404


def test_vol_surface_endpoint_empty_chain_is_502(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(
        error=EmptyChainError("no expiries"))
    assert client.get("/vol-surface/SPY").status_code == 502
