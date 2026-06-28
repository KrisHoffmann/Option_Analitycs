"""Tests for the scenario / risk matrix (V2-C).

The matrix is just the position model repriced over a 2D shock grid, so the
checks pin it against the same pure pricing the rest of the suite validates: the
base cell must equal the unshocked current value, a hand-computed BSM cell must
match, monotonicity must hold for a long call, and a short leg must negate the
change surface. The route is exercised with a built position, no network.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from pricing.black_scholes import price as bsm_price
from strategies.position import Leg, Position, current_value
from strategies.scenario import build_scenario_matrix

R = 0.04
Q = 0.0
SPOT = 100.0
VOL = 0.20
T = 0.5


def _long_call() -> Position:
    return Position(legs=(Leg("call", 1.0, "long", strike=100.0,
                              time_to_expiry=T),))


def _short_call() -> Position:
    return Position(legs=(Leg("call", 1.0, "short", strike=100.0,
                              time_to_expiry=T),))


# ---------------------------------------------------------------------------
# Pure matrix
# ---------------------------------------------------------------------------
def test_axes_match_defaults_and_dimensions():
    m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q)
    assert m.spot_shocks_pct == tuple(
        float(x) for x in range(-30, 31, 5))  # -30..+30 step 5 -> 13 cols
    assert m.vol_shocks_pp[0] == -10.0 and m.vol_shocks_pp[-1] == 10.0
    assert len(m.vol_shocks_pp) == 9
    assert len(m.values) == 9 and all(len(row) == 13 for row in m.values)
    assert len(m.changes) == 9 and all(len(row) == 13 for row in m.changes)
    # Base cell sits on the grid at 0pp / 0%.
    assert m.spot_shocks_pct[m.base_col] == 0.0
    assert m.vol_shocks_pp[m.base_row] == 0.0


def test_base_cell_is_unshocked_current_value():
    m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q)
    expected = current_value(_long_call(), [SPOT], R, VOL, Q)[0]
    assert m.base_value == pytest.approx(expected)
    assert m.values[m.base_row][m.base_col] == pytest.approx(expected)
    # Change from base is exactly zero at the base cell.
    assert m.changes[m.base_row][m.base_col] == pytest.approx(0.0)


def test_cell_matches_hand_computed_bsm():
    # A +10% spot shock and +5pp vol shock must reprice the long call to the BSM
    # price at S*1.10 and sigma+0.05, time to expiry unchanged.
    m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q)
    col = m.spot_shocks_pct.index(10.0)
    row = m.vol_shocks_pp.index(5.0)
    expected = bsm_price("call", SPOT * 1.10, 100.0, T, R, VOL + 0.05, Q)
    assert m.values[row][col] == pytest.approx(expected)


def test_long_call_value_increases_with_spot_and_vol():
    m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q)
    # Along any row, value rises with the spot shock (call delta > 0).
    for row in m.values:
        assert all(row[i] < row[i + 1] for i in range(len(row) - 1))
    # Down any column, value rises with the vol shock (call vega > 0).
    for c in range(len(m.spot_shocks_pct)):
        column = [m.values[r][c] for r in range(len(m.vol_shocks_pp))]
        assert all(column[i] < column[i + 1] for i in range(len(column) - 1))


def test_short_leg_negates_the_change_surface():
    long_m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q)
    short_m = build_scenario_matrix(_short_call(), SPOT, R, VOL, Q)
    for r in range(len(long_m.vol_shocks_pp)):
        for c in range(len(long_m.spot_shocks_pct)):
            assert short_m.changes[r][c] == pytest.approx(-long_m.changes[r][c])


def test_extreme_negative_vol_shock_clamps_to_zero_without_error():
    # A -50pp shock on a 20-vol position drives shocked vol below 0; it must clamp
    # to 0 (BSM degenerate = discounted intrinsic), not raise.
    m = build_scenario_matrix(_long_call(), SPOT, R, VOL, Q,
                              vol_shock_min_pp=-50.0, vol_shock_max_pp=10.0,
                              vol_steps=7)
    intrinsic_at_zero_vol = bsm_price("call", SPOT, 100.0, T, R, 0.0, Q)
    assert m.values[0][m.base_col] == pytest.approx(intrinsic_at_zero_vol)


def test_degenerate_grid_raises():
    with pytest.raises(ValueError):
        build_scenario_matrix(_long_call(), SPOT, R, VOL, Q, spot_steps=1)
    with pytest.raises(ValueError):
        build_scenario_matrix(_long_call(), SPOT, R, VOL, Q,
                              vol_shock_min_pp=5.0, vol_shock_max_pp=5.0)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    return TestClient(app)


def _request_body() -> dict:
    return {
        "legs": [
            {"instrument": "call", "quantity": 1.0, "side": "long",
             "strike": 100.0, "time_to_expiry": 0.5},
        ],
        "spot": 100.0,
        "risk_free_rate": 0.04,
        "volatility": 0.20,
    }


def test_scenario_endpoint_returns_matrix(client):
    resp = client.post("/position-scenario", json=_request_body())
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["spot_shocks_pct"]) == 13
    assert len(body["vol_shocks_pp"]) == 9
    assert len(body["values"]) == 9 and len(body["values"][0]) == 13
    # Base cell echoes the unshocked value, and its change is zero.
    assert body["values"][body["base_row"]][body["base_col"]] == pytest.approx(
        body["base_value"])
    assert body["changes"][body["base_row"]][body["base_col"]] == pytest.approx(
        0.0)


def test_scenario_endpoint_custom_grid(client):
    payload = _request_body()
    payload["grid"] = {
        "spot_shock_min_pct": -20.0, "spot_shock_max_pct": 20.0, "spot_steps": 5,
        "vol_shock_min_pp": -5.0, "vol_shock_max_pp": 5.0, "vol_steps": 3,
    }
    body = client.post("/position-scenario", json=payload).json()
    assert body["spot_shocks_pct"] == [-20.0, -10.0, 0.0, 10.0, 20.0]
    assert body["vol_shocks_pp"] == [-5.0, 0.0, 5.0]


def test_scenario_endpoint_empty_legs_is_422(client):
    payload = _request_body()
    payload["legs"] = []
    assert client.post("/position-scenario", json=payload).status_code == 422


def test_scenario_endpoint_bad_grid_is_422(client):
    payload = _request_body()
    payload["grid"] = {"spot_shock_min_pct": 30.0, "spot_shock_max_pct": -30.0}
    assert client.post("/position-scenario", json=payload).status_code == 422
