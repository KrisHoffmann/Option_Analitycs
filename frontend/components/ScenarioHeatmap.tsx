"use client";

import { useState } from "react";
import { money } from "@/lib/format";
import type { PositionScenarioResponse } from "@/lib/types";

// Position model value under an instantaneous shock to spot (x, multiplicative %)
// and volatility (y, additive pp). Colour is a DIVERGING blue<->amber scale
// CENTERED ON THE BASE cell (no shock): blue = lower model value, amber = higher.
// Deliberately NOT red/green -- this is mark-to-market value, never P&L, and the
// project's own two neutral chart hues carry no profit connotation. The base cell
// (current position) is ringed, and hover reads out the exact value and change.
const W = 760;
const H = 470;
const M = { top: 24, right: 22, bottom: 96, left: 66 };

// Diverging endpoints: --accent (blue) and --current (amber), through a light
// neutral at the base. Kept as literals so the SVG fills interpolate in RGB.
const BLUE = [29, 78, 216];
const NEUTRAL = [239, 242, 247];
const AMBER = [180, 83, 9];

function divergingColor(change: number, maxAbs: number): string {
  if (maxAbs <= 0) return `rgb(${NEUTRAL.join(",")})`;
  const t = Math.max(-1, Math.min(1, change / maxAbs));
  const [from, to] = t < 0 ? [NEUTRAL, BLUE] : [NEUTRAL, AMBER];
  const f = Math.abs(t);
  const c = from.map((v, i) => Math.round(v + (to[i] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

const NOTE =
  "Mark-to-market model value under an instantaneous spot/vol shock — not P&L, not a forecast.";

export default function ScenarioHeatmap({
  data,
}: {
  data: PositionScenarioResponse;
}) {
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);

  const cols = data.spot_shocks_pct.length;
  const rows = data.vol_shocks_pp.length;
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const cellW = innerW / cols;
  const cellH = innerH / rows;

  // Symmetric scale around the base so the base is the true neutral midpoint.
  const maxAbs = Math.max(
    0,
    ...data.changes.flatMap((row) => row.map((v) => Math.abs(v))),
  );

  // vol shock increases UPWARD (positive at top): row r=0 is the most negative pp.
  const yForRow = (r: number) => M.top + (rows - 1 - r) * cellH;
  const xForCol = (c: number) => M.left + c * cellW;

  const hv =
    hover != null
      ? {
          spotPct: data.spot_shocks_pct[hover.c],
          volPp: data.vol_shocks_pp[hover.r],
          value: data.values[hover.r][hover.c],
          change: data.changes[hover.r][hover.c],
        }
      : null;

  return (
    <div className="scn-chart">
      {/* hover readout (exact value + change), or the base value when idle */}
      <div className="scn-readout num" aria-live="polite">
        {hv ? (
          <>
            <span className="scn-readout-strong">
              Value ${money(hv.value)}
            </span>
            <span
              style={{
                color:
                  hv.change === 0
                    ? "var(--muted)"
                    : divergingColor(
                        hv.change < 0 ? -maxAbs : maxAbs,
                        maxAbs,
                      ),
              }}
            >
              Δ {hv.change >= 0 ? "+" : ""}
              {money(hv.change)}
            </span>
            <span>
              spot {hv.spotPct >= 0 ? "+" : ""}
              {hv.spotPct}% · vol {hv.volPp >= 0 ? "+" : ""}
              {hv.volPp}pp
            </span>
          </>
        ) : (
          <span className="scn-readout-hint">
            Hover a cell for its exact model value and change from base.
          </span>
        )}
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        role="img"
        aria-label={`Position model value under market shocks: a ${rows}-by-${cols} grid coloured by model value relative to the base (no-shock) value of ${money(
          data.base_value,
        )} dollars. Columns are spot shocks from ${data.spot_shocks_pct[0]} to ${data.spot_shocks_pct[cols - 1]} percent; rows are volatility shocks from ${data.vol_shocks_pp[0]} to ${data.vol_shocks_pp[rows - 1]} percentage points. Blue is lower model value, amber is higher.`}
      >
        {/* cells */}
        {data.values.map((row, r) =>
          row.map((value, c) => {
            const change = data.changes[r][c];
            const isBase = r === data.base_row && c === data.base_col;
            const isHover = hover?.r === r && hover?.c === c;
            return (
              <rect
                key={`${r}-${c}`}
                x={xForCol(c)}
                y={yForRow(r)}
                width={cellW}
                height={cellH}
                fill={divergingColor(change, maxAbs)}
                stroke={isHover ? "var(--ink)" : "var(--surface)"}
                strokeWidth={isHover ? 1.6 : 0.5}
                onMouseEnter={() => setHover({ r, c })}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "pointer" }}
              >
                <title>
                  {`spot ${data.spot_shocks_pct[c] >= 0 ? "+" : ""}${data.spot_shocks_pct[c]}% · vol ${data.vol_shocks_pp[r] >= 0 ? "+" : ""}${data.vol_shocks_pp[r]}pp\nvalue $${money(value)} · change ${change >= 0 ? "+" : ""}${money(change)}${isBase ? " (base)" : ""}`}
                </title>
              </rect>
            );
          }),
        )}

        {/* base cell ring -- current position, no shock */}
        <rect
          x={xForCol(data.base_col)}
          y={yForRow(data.base_row)}
          width={cellW}
          height={cellH}
          fill="none"
          stroke="var(--ink)"
          strokeWidth={2}
          pointerEvents="none"
        />
        <text
          x={xForCol(data.base_col) + cellW / 2}
          y={yForRow(data.base_row) + cellH / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize="9"
          fontWeight={600}
          fill="var(--ink)"
          pointerEvents="none"
        >
          base
        </text>

        {/* x ticks (spot shock %) */}
        {data.spot_shocks_pct.map((pct, c) => (
          <text
            key={`x${c}`}
            x={xForCol(c) + cellW / 2}
            y={M.top + innerH + 15}
            textAnchor="middle"
            fontSize="9.5"
            fill="var(--muted-2)"
            className="num"
          >
            {pct > 0 ? "+" : ""}
            {pct}
          </text>
        ))}

        {/* y ticks (vol shock pp) */}
        {data.vol_shocks_pp.map((pp, r) => (
          <text
            key={`y${r}`}
            x={M.left - 8}
            y={yForRow(r) + cellH / 2}
            textAnchor="end"
            dominantBaseline="central"
            fontSize="9.5"
            fill="var(--muted-2)"
            className="num"
          >
            {pp > 0 ? "+" : ""}
            {pp}
          </text>
        ))}

        {/* axis titles */}
        <text
          x={M.left + innerW / 2}
          y={M.top + innerH + 34}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
        >
          spot shock (%)
        </text>
        <text
          x={16}
          y={M.top + innerH / 2}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
          transform={`rotate(-90 16 ${M.top + innerH / 2})`}
        >
          vol shock (pp)
        </text>

        {/* on-chart note: visible without interaction */}
        <text
          x={M.left + innerW / 2}
          y={H - 8}
          textAnchor="middle"
          fontSize="10.5"
          fill="var(--muted)"
        >
          {NOTE}
        </text>
      </svg>

      {/* diverging legend: labelled, so colour is never the only encoding */}
      <div className="scn-legend">
        <span className="scn-legend-label">lower model value</span>
        <span className="scn-legend-bar" aria-hidden="true" />
        <span className="scn-legend-label">higher model value</span>
        <span className="scn-legend-base num">
          base ${money(data.base_value)}
        </span>
      </div>
    </div>
  );
}
