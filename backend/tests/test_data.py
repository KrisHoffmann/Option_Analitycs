"""Tests for the data layer (M5).

No network here. The yfinance mapping is exercised through its pure functions
with synthetic provider records, and the route is tested with a fake provider
injected via FastAPI's dependency override -- so the suite is deterministic and
offline, the way the data caveats in docs/architecture.md demand we treat the
source.
"""

import sys
import types
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from data import (
    EmptyChainError,
    OptionChain,
    UnsupportedTickerError,
    get_chain_provider,
    get_option_chain,
)
from data.provider import ChainFetchError
from data.yfinance_provider import (
    YFinanceProvider,
    _select_expiries,
    build_option_chain,
    record_to_quote,
)

NOW = datetime(2026, 6, 24, tzinfo=UTC)
FUTURE = date(2026, 7, 24)   # 30 days out
PAST = date(2026, 6, 1)      # already expired relative to NOW

CALL_RECORD = {
    "contractSymbol": "AAPL260724C00150000", "strike": 150.0, "lastPrice": 5.0,
    "bid": 4.9, "ask": 5.1, "volume": 100, "openInterest": 2000,
    "impliedVolatility": 0.25, "inTheMoney": True,
}
# A deliberately gappy put: missing/NaN fields, the norm for illiquid strikes.
PUT_RECORD = {
    "contractSymbol": "AAPL260724P00150000", "strike": 150.0,
    "lastPrice": float("nan"), "bid": None, "ask": 3.0,
    "volume": float("nan"), "openInterest": 50,
    "impliedVolatility": 0.27, "inTheMoney": False,
}


# ---------------------------------------------------------------------------
# Pure mapping
# ---------------------------------------------------------------------------
def test_record_to_quote_maps_fields():
    quote = record_to_quote(CALL_RECORD, "call")
    assert quote.option_type == "call"
    assert quote.strike == 150.0
    assert quote.bid == 4.9
    assert quote.implied_volatility == 0.25
    assert quote.in_the_money is True


def test_record_to_quote_normalizes_missing_to_none():
    quote = record_to_quote(PUT_RECORD, "put")
    assert quote.last_price is None   # was NaN
    assert quote.bid is None          # was None
    assert quote.volume is None       # was NaN
    assert quote.ask == 3.0


def test_build_chain_drops_past_expiries_and_computes_tte():
    chain = build_option_chain(
        "AAPL", spot=152.0, fetched_at=NOW,
        raw_expiries=[
            (FUTURE, [CALL_RECORD], [PUT_RECORD]),
            (PAST, [CALL_RECORD], [PUT_RECORD]),  # should be dropped
        ])
    assert len(chain.expiries) == 1
    assert chain.expiries[0].expiry == FUTURE
    assert chain.expiries[0].time_to_expiry == pytest.approx(30 / 365.0)


def test_build_chain_all_expired_raises_empty():
    with pytest.raises(EmptyChainError):
        build_option_chain("AAPL", spot=152.0, fetched_at=NOW,
                           raw_expiries=[(PAST, [CALL_RECORD], [PUT_RECORD])])


# ---------------------------------------------------------------------------
# Expiry sampling across the term structure (pure, no network)
# ---------------------------------------------------------------------------
# SPY-like listing: dense near-dated weeklies, then monthlies/quarterlies/LEAPs.
_SPY_EXPIRIES = [
    "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01",
    "2026-07-02", "2026-07-10", "2026-07-17", "2026-07-24", "2026-07-31",
    "2026-08-21", "2026-09-18", "2026-10-16", "2026-12-18", "2027-03-19",
    "2027-06-17", "2027-09-17", "2027-12-17", "2028-06-16", "2028-12-15",
]
_TODAY = date(2026, 6, 25)


def test_select_expiries_samples_across_the_curve_not_nearest_block():
    # The failure mode being prevented: nearest-10-contiguous is all <= ~36d.
    selected = _select_expiries(_SPY_EXPIRIES, _TODAY, max_expiries=10)
    days = [(date.fromisoformat(s) - _TODAY).days for s in selected]
    assert days == sorted(days)                 # date order
    assert min(days) <= 10                       # keeps a near weekly
    assert max(days) >= 300                      # ...AND reaches out ~1 year
    assert sum(1 for d in days if d > 45) >= 4   # real term-structure spread


def test_select_expiries_skips_past_and_today():
    selected = _select_expiries(_SPY_EXPIRIES, _TODAY, max_expiries=10)
    for s in selected:
        assert (date.fromisoformat(s) - _TODAY).days >= 1


def test_select_expiries_deduplicates_when_few_expiries():
    # All short-dated: several targets collapse onto the same expiries, so the
    # result must be de-duplicated, ordered, and a subset of the input.
    short = ["2026-06-29", "2026-07-02", "2026-07-10"]  # 4d, 7d, 15d
    selected = _select_expiries(short, _TODAY, max_expiries=10)
    assert selected                                    # non-empty
    assert len(selected) == len(set(selected))         # no duplicates
    assert selected == sorted(selected)                # date order
    assert set(selected) <= set(short)                 # subset of input


def test_select_expiries_empty_or_all_past_returns_empty():
    assert _select_expiries([], _TODAY, max_expiries=10) == []
    assert _select_expiries(["2026-06-01", "2026-06-24"], _TODAY, 10) == []


# ---------------------------------------------------------------------------
# yfinance fetch tolerance (fake yfinance module, still no real network)
# ---------------------------------------------------------------------------
class _FakeFrame:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def to_dict(self, _orient: str) -> list[dict]:
        return self._records


class _FakeTable:
    def __init__(self, calls: list[dict], puts: list[dict]) -> None:
        self.calls = _FakeFrame(calls)
        self.puts = _FakeFrame(puts)


class _FakeHandle:
    """Stand-in for yfinance.Ticker that can fail on chosen expiries."""

    def __init__(self, options: list[str], fail: set[str] | None = None) -> None:
        self.options = options
        self.fast_info = {"last_price": 100.0}
        self._fail = fail or set()

    def option_chain(self, expiry: str) -> _FakeTable:
        if expiry in self._fail:
            raise RuntimeError("simulated rate limit")
        rec = {"contractSymbol": f"X{expiry}", "strike": 100.0, "bid": 1.0,
               "ask": 1.2, "openInterest": 50, "impliedVolatility": 0.2}
        return _FakeTable([rec], [rec])


def _install_fake_yfinance(monkeypatch, handle: _FakeHandle) -> None:
    module = types.ModuleType("yfinance")
    module.Ticker = lambda _symbol: handle  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yfinance", module)


def _future_expiries(*day_offsets: int) -> list[str]:
    today = datetime.now(UTC).date()
    return [(today + timedelta(days=d)).isoformat() for d in day_offsets]


def test_get_option_chain_tolerates_partial_expiry_failure(monkeypatch):
    # Some expiries succeed, one fails mid-loop (the common prod failure): the
    # surviving slices must still come back, not be discarded wholesale.
    exps = _future_expiries(30, 60, 90)
    handle = _FakeHandle(exps, fail={exps[1]})  # the 60d fetch errors
    _install_fake_yfinance(monkeypatch, handle)

    chain = YFinanceProvider().get_option_chain("AAPL")

    got = {e.expiry.isoformat() for e in chain.expiries}
    assert exps[0] in got and exps[2] in got
    assert exps[1] not in got


def test_get_option_chain_all_expiries_fail_raises_fetch_error(monkeypatch):
    exps = _future_expiries(30, 60, 90)
    handle = _FakeHandle(exps, fail=set(exps))  # every fetch errors
    _install_fake_yfinance(monkeypatch, handle)

    with pytest.raises(ChainFetchError):
        YFinanceProvider().get_option_chain("AAPL")


# ---------------------------------------------------------------------------
# Service-level ticker validation (with a fake provider, no network)
# ---------------------------------------------------------------------------
class _FakeProvider:
    def __init__(self, chain=None, error=None):
        self._chain = chain
        self._error = error
        self.calls: list[str] = []

    def get_option_chain(self, ticker: str) -> OptionChain:
        self.calls.append(ticker)
        if self._error is not None:
            raise self._error
        return self._chain


def _sample_chain() -> OptionChain:
    return build_option_chain("AAPL", 152.0, datetime.now(UTC),
                              [(date.today() + timedelta(days=30),
                                [CALL_RECORD], [PUT_RECORD])])


def test_get_option_chain_rejects_unsupported_ticker():
    provider = _FakeProvider(chain=_sample_chain())
    with pytest.raises(UnsupportedTickerError):
        get_option_chain("DOGE", provider=provider)
    assert provider.calls == []  # never reached the provider


def test_get_option_chain_normalizes_symbol_and_delegates():
    provider = _FakeProvider(chain=_sample_chain())
    chain = get_option_chain("  aapl ", provider=provider)
    assert provider.calls == ["AAPL"]
    assert chain.ticker == "AAPL"


# ---------------------------------------------------------------------------
# Routes (dependency-injected fake provider)
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_tickers_endpoint(client):
    body = client.get("/tickers").json()
    assert "AAPL" in body["tickers"]


def test_chain_endpoint_returns_serialized_chain(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(
        chain=_sample_chain())
    resp = client.get("/chain/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["spot"] == 152.0
    assert len(body["expiries"]) == 1
    assert body["expiries"][0]["calls"][0]["strike"] == 150.0


def test_chain_endpoint_unsupported_ticker_is_404(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(
        chain=_sample_chain())
    assert client.get("/chain/DOGE").status_code == 404


def test_chain_endpoint_empty_chain_is_502(client):
    app.dependency_overrides[get_chain_provider] = lambda: _FakeProvider(
        error=EmptyChainError("no expiries"))
    resp = client.get("/chain/AAPL")
    assert resp.status_code == 502
