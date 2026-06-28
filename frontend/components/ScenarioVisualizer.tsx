"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, fetchPositionScenario } from "@/lib/api";
import { money } from "@/lib/format";
import { PRESETS, type UiLeg, toLegInput } from "@/lib/position";
import type { PositionScenarioResponse } from "@/lib/types";
import InfoTip from "./InfoTip";
import LegBuilder from "./LegBuilder";
import ScenarioHeatmap from "./ScenarioHeatmap";

export default function ScenarioVisualizer() {
  const [legs, setLegs] = useState<UiLeg[]>(() => PRESETS[1].build()); // straddle
  const [spot, setSpot] = useState(100);
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [volatility, setVolatility] = useState(0.25);
  const [dividendYield, setDividendYield] = useState(0);

  const [data, setData] = useState<PositionScenarioResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce so editing a number field doesn't fire a request per keystroke.
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (legs.length === 0) {
      setData(null);
      setError(null);
      return;
    }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setLoading(true);
      fetchPositionScenario({
        legs: legs.map(toLegInput),
        spot,
        risk_free_rate: riskFreeRate,
        volatility,
        dividend_yield: dividendYield,
      })
        .then((response) => {
          setData(response);
          setError(null);
        })
        .catch((err: unknown) => {
          setError(
            err instanceof ApiError
              ? err.message
              : "Something went wrong computing the scenario matrix.",
          );
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [legs, spot, riskFreeRate, volatility, dividendYield]);

  return (
    <div className="shell">
      {/* ---------- left: inputs ---------- */}
      <div>
        <LegBuilder legs={legs} onChange={setLegs} />

        <div className="panel" style={{ marginTop: 24 }}>
          <div className="panel-head">
            <h2>Market parameters</h2>
          </div>
          <div className="panel-body">
            <div className="params-grid">
              <div className="field">
                <label htmlFor="scn-spot">
                  Spot <span className="unit">($)</span>
                  <InfoTip k="spot" />
                </label>
                <input
                  id="scn-spot"
                  type="number"
                  min={0}
                  step={1}
                  value={spot}
                  onChange={(e) => setSpot(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="scn-rate">
                  Risk-free rate <span className="unit">(decimal)</span>
                  <InfoTip k="riskFreeRate" />
                </label>
                <input
                  id="scn-rate"
                  type="number"
                  step={0.005}
                  value={riskFreeRate}
                  onChange={(e) => setRiskFreeRate(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="scn-vol">
                  Volatility <span className="unit">(decimal)</span>
                  <InfoTip k="volatility" />
                </label>
                <input
                  id="scn-vol"
                  type="number"
                  min={0}
                  step={0.01}
                  value={volatility}
                  onChange={(e) => setVolatility(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="scn-div">
                  Dividend yield <span className="unit">(decimal)</span>
                  <InfoTip k="dividendYield" />
                </label>
                <input
                  id="scn-div"
                  type="number"
                  min={0}
                  step={0.005}
                  value={dividendYield}
                  onChange={(e) => setDividendYield(Number(e.target.value))}
                />
              </div>
            </div>
            <p className="hint">
              The matrix shocks spot by ±30% (multiplicative) and volatility by
              ±10 pp (additive) around these values, holding each leg&rsquo;s time
              to expiry fixed — an instantaneous shock. Decimals: 0.04 = 4%.
            </p>
          </div>
        </div>
      </div>

      {/* ---------- right: heatmap ---------- */}
      <div>
        <div className="panel chart-card">
          <div className="panel-head">
            <h2>Position value under market shocks</h2>
            {loading && (
              <span className="hint" style={{ margin: 0 }}>
                updating…
              </span>
            )}
          </div>
          <div className="panel-body">
            {error ? (
              <p className="error">{error}</p>
            ) : data ? (
              <>
                <div className="scn-base-strip">
                  <div className="scn-base-item">
                    <span className="scn-base-label">Base model value</span>
                    <span className="scn-base-value num">
                      ${money(data.base_value)}
                    </span>
                    <span className="scn-base-sub">current position, no shock</span>
                  </div>
                  <div className="scn-base-item">
                    <span className="scn-base-label">Anchored at</span>
                    <span className="scn-base-value num">
                      ${money(data.spot)} · {(data.base_volatility * 100).toFixed(0)}% vol
                    </span>
                    <span className="scn-base-sub">
                      spot &amp; volatility before any shock
                    </span>
                  </div>
                </div>
                <ScenarioHeatmap data={data} />
              </>
            ) : (
              <p className="skeleton">
                {legs.length === 0
                  ? "Add a leg or pick a preset to build a position."
                  : "Computing the scenario matrix…"}
              </p>
            )}
          </div>
        </div>

        <div className="panel" style={{ marginTop: 24 }}>
          <div className="panel-body surf-limits">
            <h3>Reading this honestly</h3>
            <ul>
              <li>
                <strong>Value, not P&amp;L.</strong> Each cell is the
                position&rsquo;s mark-to-market <em>model</em> value if spot and
                volatility moved to that shock right now. A change in model value
                is not a realized profit or loss, and nothing here is a forecast
                of where the market will go.
              </li>
              <li>
                <strong>Instantaneous shock.</strong> Each leg&rsquo;s time to
                expiry is held fixed — only spot and volatility move. Time decay
                (theta) is not applied across the grid.
              </li>
              <li>
                <strong>One flat volatility, shocked uniformly.</strong> Every leg
                is revalued at a single volatility (shocked in percentage points);
                a per-strike volatility smile is a separate, surface-level concern.
                Constant <span className="num">r</span> and{" "}
                <span className="num">q</span>, European exercise.
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
