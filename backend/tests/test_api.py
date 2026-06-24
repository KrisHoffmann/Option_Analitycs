"""API contract tests (M4) via FastAPI's TestClient.

These check that routes parse, delegate to the (separately validated) math, and
serialize correctly -- and that domain errors come back as 422, not 500. The
numerical correctness itself is covered by the pricing/strategies test modules.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

# Hull reference contract (see test_black_scholes): call price ~ 4.7594.
HULL = dict(option_type="call", spot=42, strike=40, time_to_expiry=0.5,
            risk_free_rate=0.10, volatility=0.20)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_price_returns_price_and_greeks():
    resp = client.post("/price", json=HULL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["price"] == pytest.approx(4.7594, abs=1e-3)
    assert set(body["greeks"]) == {"delta", "gamma", "theta", "vega", "rho"}
    assert body["greeks"]["delta"] == pytest.approx(0.779, abs=5e-3)


def test_price_rejects_invalid_input():
    bad = {**HULL, "spot": -1}
    assert client.post("/price", json=bad).status_code == 422


def test_price_comparison_endpoint():
    resp = client.post("/price-comparison", json={"contract": HULL, "steps": 200})
    assert resp.status_code == 200
    body = resp.json()
    # CRR European tracks BSM; an American call on a non-dividend stock adds no
    # early-exercise premium.
    assert body["crr_european"] == pytest.approx(body["bsm_price"], abs=0.02)
    assert body["early_exercise_premium"] == pytest.approx(0.0, abs=1e-6)
    assert set(body["greeks"]) == {"delta", "gamma", "theta", "vega", "rho"}
    assert body["steps"] == 200


def test_price_comparison_american_put_has_premium():
    contract = {"option_type": "put", "spot": 85, "strike": 100,
                "time_to_expiry": 1.0, "risk_free_rate": 0.06, "volatility": 0.30}
    body = client.post("/price-comparison",
                       json={"contract": contract, "steps": 200}).json()
    assert body["crr_american"] > body["crr_european"]
    assert body["early_exercise_premium"] > 1e-3


def test_implied_volatility_roundtrip():
    market = client.post("/price", json=HULL).json()["price"]
    resp = client.post("/implied-volatility", json={
        "option_type": "call", "market_price": market, "spot": 42,
        "strike": 40, "time_to_expiry": 0.5, "risk_free_rate": 0.10})
    assert resp.status_code == 200
    assert resp.json()["implied_volatility"] == pytest.approx(0.20, abs=1e-4)


def test_implied_volatility_below_intrinsic_is_422():
    resp = client.post("/implied-volatility", json={
        "option_type": "call", "market_price": 1.0, "spot": 100,
        "strike": 80, "time_to_expiry": 1.0, "risk_free_rate": 0.05})
    assert resp.status_code == 422
    assert "intrinsic" in resp.json()["detail"]


def test_position_returns_curves_and_net_greeks():
    # Bull call spread 95/105.
    resp = client.post("/position", json={
        "legs": [
            {"instrument": "call", "quantity": 1, "side": "long",
             "strike": 95, "time_to_expiry": 0.5},
            {"instrument": "call", "quantity": 1, "side": "short",
             "strike": 105, "time_to_expiry": 0.5},
        ],
        "grid": {"spot_min": 50, "spot_max": 150, "num_points": 101},
        "spot": 100, "risk_free_rate": 0.04, "volatility": 0.25})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["spots"]) == 101
    assert len(body["payoff_at_expiry"]) == 101
    assert len(body["current_value"]) == 101
    assert max(body["payoff_at_expiry"]) == pytest.approx(10.0)  # spread width
    assert min(body["payoff_at_expiry"]) == pytest.approx(0.0)
    assert set(body["net_greeks"]) == {"delta", "gamma", "theta", "vega", "rho"}
    assert body["net_greeks_spot"] == 100


def test_position_invalid_legs_is_422():
    # An underlying leg may not carry a strike.
    resp = client.post("/position", json={
        "legs": [{"instrument": "underlying", "quantity": 1, "side": "long",
                  "strike": 100}],
        "grid": {"spot_min": 50, "spot_max": 150},
        "spot": 100, "volatility": 0.2})
    assert resp.status_code == 422


def test_sensitivity_returns_aligned_series():
    resp = client.post("/sensitivity", json={
        "contract": HULL,
        "variable": "spot", "metric": "delta",
        "variable_min": 30, "variable_max": 55, "num_points": 26})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["variable_values"]) == 26
    assert len(body["metric_values"]) == 26
    # Call delta rises with spot and stays within [0, 1].
    deltas = body["metric_values"]
    assert all(b >= a for a, b in zip(deltas, deltas[1:], strict=False))
    assert deltas[0] >= 0.0 and deltas[-1] <= 1.0
