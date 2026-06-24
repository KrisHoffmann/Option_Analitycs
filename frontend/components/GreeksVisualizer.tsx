"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, fetchPrice, fetchSensitivity } from "@/lib/api";
import { decimals, money } from "@/lib/format";
import type { GlossaryKey } from "@/lib/glossary";
import type {
  Greeks,
  OptionType,
  SensitivityMetric,
  SensitivityVariable,
} from "@/lib/types";
import InfoTip from "./InfoTip";
import ModelComparison from "./ModelComparison";
import SensitivityChart from "./SensitivityChart";
import Slider from "./Slider";

// The five Greeks as small multiples, with honest unit labels matching the
// backend's raw-derivative convention (backend/pricing/black_scholes.py).
const METRICS: { key: keyof Greeks; title: string; unit: string }[] = [
  { key: "delta", title: "Delta", unit: "per $1 spot" },
  { key: "gamma", title: "Gamma", unit: "per $1 spot²" },
  { key: "theta", title: "Theta", unit: "per year" },
  { key: "vega", title: "Vega", unit: "per 1.00 vol" },
  { key: "rho", title: "Rho", unit: "per 1.00 rate" },
];

// The three swept axes. Each slider's range is also the chart's x-range, so the
// current-point marker is always in view.
const X_VARS: Record<
  "spot" | "time_to_expiry" | "volatility",
  { label: string; axis: string; min: number; max: number; step: number }
> = {
  spot: { label: "Spot", axis: "Spot ($)", min: 20, max: 200, step: 1 },
  time_to_expiry: {
    label: "Time",
    axis: "Time to expiry (yr)",
    min: 0.02,
    max: 2,
    step: 0.02,
  },
  volatility: {
    label: "Volatility",
    axis: "Volatility (decimal)",
    min: 0.05,
    max: 1,
    step: 0.01,
  },
};

type XVar = keyof typeof X_VARS;
type Series = Record<string, { xs: number[]; ys: number[] }>;

export default function GreeksVisualizer() {
  const [optionType, setOptionType] = useState<OptionType>("call");
  const [strike, setStrike] = useState(100);
  const [riskFreeRate, setRiskFreeRate] = useState(0.04);
  const [spot, setSpot] = useState(100);
  const [timeToExpiry, setTimeToExpiry] = useState(0.5);
  const [volatility, setVolatility] = useState(0.25);
  const [xVar, setXVar] = useState<XVar>("spot");

  const [series, setSeries] = useState<Series | null>(null);
  const [point, setPoint] = useState<(Greeks & { price: number }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      const contract = {
        option_type: optionType,
        spot,
        strike,
        time_to_expiry: timeToExpiry,
        risk_free_rate: riskFreeRate,
        volatility,
      };
      const range = X_VARS[xVar];
      const curves = METRICS.map((m) =>
        fetchSensitivity({
          contract,
          variable: xVar as SensitivityVariable,
          metric: m.key as SensitivityMetric,
          variable_min: range.min,
          variable_max: range.max,
          num_points: 81,
        }),
      );
      Promise.all([Promise.all(curves), fetchPrice(contract)])
        .then(([curveResults, priceResult]) => {
          const next: Series = {};
          METRICS.forEach((m, i) => {
            next[m.key] = {
              xs: curveResults[i].variable_values,
              ys: curveResults[i].metric_values,
            };
          });
          setSeries(next);
          setPoint({ ...priceResult.greeks, price: priceResult.price });
          setError(null);
        })
        .catch((err: unknown) => {
          setError(
            err instanceof ApiError
              ? err.message
              : "Something went wrong computing the Greeks.",
          );
        });
    }, 180);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
  }, [optionType, strike, riskFreeRate, spot, timeToExpiry, volatility, xVar]);

  const markerX =
    xVar === "spot" ? spot : xVar === "time_to_expiry" ? timeToExpiry : volatility;

  return (
    <div className="shell">
      {/* ---------- controls ---------- */}
      <div>
        <div className="panel">
          <div className="panel-head">
            <h2>Contract</h2>
          </div>
          <div className="panel-body">
            <div className="params-grid">
              <div className="field">
                <label htmlFor="g-type">Type</label>
                <select
                  id="g-type"
                  value={optionType}
                  onChange={(e) => setOptionType(e.target.value as OptionType)}
                >
                  <option value="call">Call</option>
                  <option value="put">Put</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="g-strike">
                  Strike <span className="unit">($)</span>
                  <InfoTip k="strike" />
                </label>
                <input
                  id="g-strike"
                  type="number"
                  min={1}
                  step={1}
                  value={strike}
                  onChange={(e) => setStrike(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="g-rate">
                  Risk-free rate <span className="unit">(dec.)</span>
                  <InfoTip k="riskFreeRate" />
                </label>
                <input
                  id="g-rate"
                  type="number"
                  step={0.005}
                  value={riskFreeRate}
                  onChange={(e) => setRiskFreeRate(Number(e.target.value))}
                />
              </div>
              <div className="field stat">
                <label>
                  Model price
                  <InfoTip k="modelPrice" />
                </label>
                <span className="stat-value num">
                  {point ? `$${money(point.price)}` : "—"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 24 }}>
          <div className="panel-head">
            <h2>Inputs</h2>
          </div>
          <div className="panel-body">
            <Slider
              id="g-spot"
              label="Spot"
              unit="($)"
              min={X_VARS.spot.min}
              max={X_VARS.spot.max}
              step={X_VARS.spot.step}
              value={spot}
              display={money(spot)}
              onChange={setSpot}
              infoKey="spot"
            />
            <Slider
              id="g-time"
              label="Time to expiry"
              unit="(yr)"
              min={X_VARS.time_to_expiry.min}
              max={X_VARS.time_to_expiry.max}
              step={X_VARS.time_to_expiry.step}
              value={timeToExpiry}
              display={decimals(timeToExpiry, 2)}
              onChange={setTimeToExpiry}
              infoKey="timeToExpiry"
            />
            <Slider
              id="g-vol"
              label="Volatility"
              unit="(dec.)"
              min={X_VARS.volatility.min}
              max={X_VARS.volatility.max}
              step={X_VARS.volatility.step}
              value={volatility}
              display={decimals(volatility, 2)}
              onChange={setVolatility}
              infoKey="volatility"
            />
            <p className="hint">European exercise · no dividends (q = 0).</p>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 24 }}>
          <div className="panel-head">
            <h2>Chart x-axis</h2>
          </div>
          <div className="panel-body">
            <div className="segmented" role="group" aria-label="Chart x-axis">
              {(Object.keys(X_VARS) as XVar[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={xVar === key ? "active" : ""}
                  aria-pressed={xVar === key}
                  onClick={() => setXVar(key)}
                >
                  {X_VARS[key].label}
                </button>
              ))}
            </div>
            <p className="hint">
              Each Greek is plotted against {X_VARS[xVar].axis.toLowerCase()};
              the other inputs stay fixed at the slider values. The amber marker
              is the current point.
            </p>
          </div>
        </div>

        <ModelComparison
          contract={{
            option_type: optionType,
            spot,
            strike,
            time_to_expiry: timeToExpiry,
            risk_free_rate: riskFreeRate,
            volatility,
          }}
        />
      </div>

      {/* ---------- small multiples ---------- */}
      <div>
        {error && <p className="error">{error}</p>}
        <div className="sm-grid">
          {METRICS.map((m) => {
            const s = series?.[m.key];
            if (!s || !point) {
              return (
                <div className="sm-cell" key={m.key}>
                  <div className="sm-head">
                    <div>
                      <span className="sm-title">{m.title}</span>
                      <InfoTip k={m.key as GlossaryKey} />
                      <span className="sm-unit">{m.unit}</span>
                    </div>
                  </div>
                  <div className="sm-skeleton">computing…</div>
                </div>
              );
            }
            return (
              <SensitivityChart
                key={m.key}
                title={m.title}
                unit={m.unit}
                xLabel={X_VARS[xVar].axis}
                xs={s.xs}
                ys={s.ys}
                markerX={markerX}
                markerY={point[m.key]}
                valueText={decimals(point[m.key], 4)}
                infoKey={m.key as GlossaryKey}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
