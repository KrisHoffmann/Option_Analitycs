"""Tests for the pure realized-volatility series (V2-B).

Numerics validated against hand-computable references (docs/finance-standards.md):
a synthetic price path whose per-step volatility is known by construction, so the
annualization (x sqrt 252) and the rolling-window alignment are checked against
arithmetic, not against the implementation restating itself.
"""

import math

import pytest

from pricing.realized_vol import (
    annualized_realized_vol,
    log_returns,
    rolling_realized_vol,
)


def _geometric_closes(returns: list[float], start: float = 100.0) -> list[float]:
    """A price path whose log returns are exactly `returns` (P_t = P_{t-1} e^r)."""
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * math.exp(r))
    return closes


# ---------------------------------------------------------------------------
# Log returns
# ---------------------------------------------------------------------------
def test_log_returns_recovers_constructed_returns():
    returns = [0.01, -0.02, 0.015]
    closes = _geometric_closes(returns)
    got = log_returns(closes)
    assert got == pytest.approx(returns)


def test_log_returns_rejects_non_positive_close():
    with pytest.raises(ValueError):
        log_returns([100.0, 0.0, 101.0])


# ---------------------------------------------------------------------------
# Scalar annualized vol -- hand-computed reference
# ---------------------------------------------------------------------------
def test_annualized_vol_matches_hand_computation():
    # returns [+a, -a, +a, -a], mean 0, so the sample variance (ddof=1) is
    # sum(x^2)/(n-1) = 4a^2/3, std = a*sqrt(4/3), annualized * sqrt(252).
    a = 0.01
    returns = [a, -a, a, -a]
    expected = a * math.sqrt(4 / 3) * math.sqrt(252)
    assert annualized_realized_vol(returns) == pytest.approx(expected)
    # Sanity on the magnitude: ~0.1833.
    assert annualized_realized_vol(returns) == pytest.approx(0.183313, abs=1e-5)


def test_annualization_uses_252_not_365():
    a = 0.01
    returns = [a, -a, a, -a]
    daily = a * math.sqrt(4 / 3)
    assert annualized_realized_vol(returns, trading_days=252) == pytest.approx(
        daily * math.sqrt(252))
    # The common silent error would be sqrt(365); confirm we are NOT doing that.
    assert annualized_realized_vol(returns) != pytest.approx(daily * math.sqrt(365))


def test_annualized_vol_needs_two_returns():
    with pytest.raises(ValueError):
        annualized_realized_vol([0.01])


# ---------------------------------------------------------------------------
# Rolling series -- alignment and recovery of a known vol
# ---------------------------------------------------------------------------
def test_rolling_series_recovers_known_constant_vol():
    # A path with alternating +-a returns has, for any even window, exactly half
    # up and half down moves: mean 0, std a*sqrt(W/(W-1)). With W=20 every window
    # recovers the same annualized vol, so the series is a flat known line.
    a = 0.01
    window = 20
    returns = [a if i % 2 == 0 else -a for i in range(40)]
    closes = _geometric_closes(returns)  # 41 closes
    expected = a * math.sqrt(window / (window - 1)) * math.sqrt(252)

    series = rolling_realized_vol(closes, window=window)
    defined = [v for v in series if v is not None]
    assert all(v == pytest.approx(expected) for v in defined)


def test_rolling_series_alignment_and_warmup():
    # Length matches closes; the first `window` entries are None (warm-up), the
    # rest are defined -- so the series lines up element-for-element with dates.
    returns = [0.01 if i % 2 == 0 else -0.01 for i in range(30)]
    closes = _geometric_closes(returns)  # 31 closes
    window = 21

    series = rolling_realized_vol(closes, window=window)
    assert len(series) == len(closes)
    assert series[:window] == [None] * window
    assert all(v is not None for v in series[window:])
    # The first defined point is at index `window`: it uses returns ending at
    # close `window`, i.e. closes[0..window].
    assert series[window] is not None


def test_rolling_series_constant_geometric_series_has_zero_vol():
    # A truly constant-rate path (every return identical) has zero dispersion, so
    # realized vol is 0 -- the degenerate boundary, handled, not a divide error.
    closes = _geometric_closes([0.005] * 30)
    series = rolling_realized_vol(closes, window=21)
    assert series[-1] == pytest.approx(0.0)


def test_rolling_series_rejects_small_window():
    with pytest.raises(ValueError):
        rolling_realized_vol([100.0, 101.0, 102.0], window=1)
