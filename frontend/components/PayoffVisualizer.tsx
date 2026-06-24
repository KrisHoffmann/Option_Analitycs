"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, fetchPosition } from "@/lib/api";
import {
  PRESETS,
  type UiLeg,
  deriveGrid,
  optionStrikes,
  toLegInput,
} from "@/lib/position";
import type { PositionResponse } from "@/lib/types";
import InfoTip from "./InfoTip";
import LegBuilder from "./LegBuilder";
import NetGreeksTable from "./NetGreeksTable";
import PayoffChart from "./PayoffChart";

export default function PayoffVisualizer() {
  const [legs, setLegs] = useState<UiLeg[]>(() => PRESETS[0].build());
  const [spot, setSpot] = useState(100);
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [volatility, setVolatility] = useState(0.25);

  const [data, setData] = useState<PositionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce so dragging a number field doesn't fire a request per keystroke.
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (legs.length === 0) {
      setData(null);
      setError(null);
      return;
    }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      const request = {
        legs: legs.map(toLegInput),
        grid: deriveGrid(spot, legs),
        spot,
        risk_free_rate: riskFreeRate,
        volatility,
      };
      setLoading(true);
      fetchPosition(request)
        .then((response) => {
          setData(response);
          setError(null);
        })
        .catch((err: unknown) => {
          setError(
            err instanceof ApiError
              ? err.message
              : "Something went wrong computing the position.",
          );
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [legs, spot, riskFreeRate, volatility]);

  const strikes = optionStrikes(legs);

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
                <label htmlFor="spot">
                  Spot <span className="unit">($)</span>
                  <InfoTip k="spot" />
                </label>
                <input
                  id="spot"
                  type="number"
                  min={0}
                  step={1}
                  value={spot}
                  onChange={(e) => setSpot(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="rate">
                  Risk-free rate <span className="unit">(decimal)</span>
                  <InfoTip k="riskFreeRate" />
                </label>
                <input
                  id="rate"
                  type="number"
                  step={0.005}
                  value={riskFreeRate}
                  onChange={(e) => setRiskFreeRate(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="vol">
                  Volatility <span className="unit">(decimal)</span>
                  <InfoTip k="volatility" />
                </label>
                <input
                  id="vol"
                  type="number"
                  min={0}
                  step={0.01}
                  value={volatility}
                  onChange={(e) => setVolatility(Number(e.target.value))}
                />
              </div>
            </div>
            <p className="hint">
              Rates and volatility are decimals: 0.04 = 4%. European exercise,
              no dividends (q = 0), constant rate and volatility.
            </p>
          </div>
        </div>
      </div>

      {/* ---------- right: outputs ---------- */}
      <div>
        <div className="panel chart-card">
          <div className="panel-head">
            <h2>Payoff &amp; current value</h2>
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
              <PayoffChart
                spots={data.spots}
                payoff={data.payoff_at_expiry}
                currentValue={data.current_value}
                strikes={strikes}
                currentSpot={data.net_greeks_spot}
              />
            ) : (
              <p className="skeleton">
                {legs.length === 0
                  ? "Add a leg to plot the position."
                  : "Computing payoff curves…"}
              </p>
            )}
          </div>
          {data && !error && (
            <div className="legend">
              <span className="legend-item">
                <span
                  className="legend-swatch"
                  style={{ borderTopColor: "var(--payoff)" }}
                />
                Payoff at expiry
              </span>
              <span className="legend-item">
                <span
                  className="legend-swatch"
                  style={{
                    borderTopColor: "var(--current)",
                    borderTopStyle: "dashed",
                  }}
                />
                Current value (model)
              </span>
            </div>
          )}
        </div>

        {data && !error && (
          <div style={{ marginTop: 24 }}>
            <NetGreeksTable greeks={data.net_greeks} spot={data.net_greeks_spot} />
          </div>
        )}
      </div>
    </div>
  );
}
