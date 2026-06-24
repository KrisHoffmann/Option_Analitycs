"""Tests for the data layer (M5).

No network here. The yfinance mapping is exercised through its pure functions
with synthetic provider records, and the route is tested with a fake provider
injected via FastAPI's dependency override -- so the suite is deterministic and
offline, the way the data caveats in docs/architecture.md demand we treat the
source.
"""

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
from data.yfinance_provider import build_option_chain, record_to_quote

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
