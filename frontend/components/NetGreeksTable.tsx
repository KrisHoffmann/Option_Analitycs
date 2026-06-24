import type { Greeks } from "@/lib/types";
import type { GlossaryKey } from "@/lib/glossary";
import { decimals } from "@/lib/format";
import InfoTip from "./InfoTip";

interface NetGreeksTableProps {
  greeks: Greeks;
  spot: number;
}

// Units are stated honestly and match the backend's raw-derivative convention
// (see backend/pricing/black_scholes.py). delta/gamma per $1 of spot; vega and
// rho per 1.00 (i.e. +100 points) of vol/rate; theta per year.
const ROWS: { key: keyof Greeks; name: string; unit: string }[] = [
  { key: "delta", name: "Delta", unit: "per $1 spot" },
  { key: "gamma", name: "Gamma", unit: "per $1 spot²" },
  { key: "theta", name: "Theta", unit: "per year" },
  { key: "vega", name: "Vega", unit: "per 1.00 vol" },
  { key: "rho", name: "Rho", unit: "per 1.00 rate" },
];

export default function NetGreeksTable({ greeks, spot }: NetGreeksTableProps) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Net Greeks</h2>
        <span className="hint num" style={{ margin: 0 }}>
          evaluated at spot {spot.toLocaleString("en-US")}
        </span>
      </div>
      <div className="panel-body" style={{ padding: 0 }}>
        <div className="greeks-grid">
          {ROWS.map(({ key, name, unit }) => {
            const value = greeks[key];
            return (
              <div className="greek" key={key}>
                <span className="greek-name">
                  {name}
                  <InfoTip k={key as GlossaryKey} />
                </span>
                <span className={`greek-value num${value < 0 ? " neg" : ""}`}>
                  {decimals(value, 4)}
                </span>
                <span className="greek-unit">{unit}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
