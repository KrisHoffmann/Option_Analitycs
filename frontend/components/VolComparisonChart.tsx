"use client";

import { useId } from "react";
import { niceTicks } from "@/lib/scale";
import type { RealizedVolPoint } from "@/lib/types";

// Implied vs realized volatility over time. The whole point of the chart is to
// make the forward/backward asymmetry *visually literal*, so the geometry is
// deliberate and not symmetric:
//
//   - The realized-vol curve (solid blue) runs LEFT across the history -- it is
//     a backward-looking series, one point per trailing window.
//   - Today's ATM implied vol (amber) is a SINGLE forward observation: a marker
//     at "today" projected to the right across the option's remaining life. It is
//     never drawn back across history (we never observed it there), so the
//     forward leg is a short stub, not a flat line spanning the chart.
//   - The vertical gap between the end of the realized curve and the implied
//     marker, at today, is the premium -- bracketed and labelled on the chart.
//
// The y-axis is anchored at zero so the premium gap is never visually
// exaggerated by a truncated baseline. Colours are the project's blue/amber and
// carry no profit/loss meaning.
const W = 820;
const H = 460;
const M = { top: 26, right: 26, bottom: 92, left: 56 };
const MS_PER_DAY = 86_400_000;

interface VolComparisonChartProps {
  ticker: string;
  realized: RealizedVolPoint[];
  windowDays: number; // realized rolling window (trading days)
  impliedAtmVol: number | null;
  impliedDaysToExpiry: number | null;
  premiumNote: string; // the mandatory framing, rendered on the chart
}

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

export default function VolComparisonChart({
  ticker,
  realized,
  windowDays,
  impliedAtmVol,
  impliedDaysToExpiry,
  premiumNote,
}: VolComparisonChartProps) {
  const clipId = useId();
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;

  if (realized.length === 0) {
    return (
      <p className="skeleton">No realized-volatility history to plot.</p>
    );
  }

  const pts = realized.map((p) => ({ t: Date.parse(p.date), v: p.realized_vol }));
  const xToday = pts[pts.length - 1].t; // realized ends at the latest close
  const latestRealized = pts[pts.length - 1].v;
  const dte = impliedDaysToExpiry ?? 30;
  const xForwardEnd = xToday + dte * MS_PER_DAY;

  const xMin = pts[0].t;
  const xPad = (xForwardEnd - xMin) * 0.015;
  const xLo = xMin - xPad;
  const xHi = xForwardEnd + xPad;

  // Zero-anchored y so the premium gap reads at true scale (honest baseline).
  const vols = pts.map((p) => p.v);
  if (impliedAtmVol !== null) vols.push(impliedAtmVol);
  const yHi = Math.max(...vols) * 1.15 || 0.1;

  const xScale = (t: number) => M.left + ((t - xLo) / (xHi - xLo)) * innerW;
  const yScale = (v: number) => M.top + (1 - v / yHi) * innerH;

  const yTicks = niceTicks(0, yHi, 5).filter((t) => t >= 0 && t <= yHi);
  const xTicks = Array.from(
    { length: 6 },
    (_, i) => xLo + ((xHi - xLo) * i) / 5,
  );

  const realizedPath = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${xScale(p.t)},${yScale(p.v)}`)
    .join(" ");

  const xTodayPx = xScale(xToday);
  const premium = impliedAtmVol !== null ? impliedAtmVol - latestRealized : null;

  const ariaLabel =
    `Implied versus realized volatility for ${ticker}. ` +
    `Realized volatility is drawn as a backward-looking line over the trailing history; ` +
    (impliedAtmVol !== null
      ? `today's at-the-money implied volatility of ${(impliedAtmVol * 100).toFixed(1)} percent is shown as a forward marker projecting ${dte} days to the right, ` +
        `and the premium over the latest realized volatility of ${(latestRealized * 100).toFixed(1)} percent is ${((premium ?? 0) * 100).toFixed(1)} volatility points.`
      : `today's at-the-money implied volatility could not be solved for this expiry, so only the realized history is shown.`);

  return (
    <div className="vc-chart">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        role="img"
        aria-label={ariaLabel}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={M.left} y={M.top} width={innerW} height={innerH} />
          </clipPath>
        </defs>

        {/* Forward region: the option's remaining life, to the right of today.
            Shaded amber to read as "expectation", distinct from realized history. */}
        <rect
          x={xTodayPx}
          y={M.top}
          width={Math.max(0, M.left + innerW - xTodayPx)}
          height={innerH}
          fill="rgba(180,83,9,0.05)"
        />
        <text
          x={(xTodayPx + (M.left + innerW)) / 2}
          y={M.top + 13}
          textAnchor="middle"
          fontSize="10"
          fill="var(--current)"
        >
          forward · {dte}d
        </text>

        {/* y grid + ticks (volatility, %) */}
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke="var(--grid)"
              strokeWidth={1}
            />
            <text
              x={M.left - 8}
              y={yScale(t)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="10"
              fill="var(--muted-2)"
              className="num"
            >
              {(t * 100).toFixed(0)}%
            </text>
          </g>
        ))}

        {/* x ticks (dates) */}
        {xTicks.map((t) => (
          <text
            key={`x${t}`}
            x={xScale(t)}
            y={M.top + innerH + 16}
            textAnchor="middle"
            fontSize="10"
            fill="var(--muted-2)"
            className="num"
          >
            {fmtDate(t)}
          </text>
        ))}

        {/* "today" divider between the backward history and the forward region */}
        <line
          x1={xTodayPx}
          x2={xTodayPx}
          y1={M.top}
          y2={M.top + innerH}
          stroke="var(--zero-line)"
          strokeWidth={1}
          strokeDasharray="4 3"
        />
        <text
          x={xTodayPx - 5}
          y={M.top + innerH - 6}
          textAnchor="end"
          fontSize="9.5"
          fill="var(--muted-2)"
        >
          today
        </text>

        {/* axis titles */}
        <text
          x={13}
          y={M.top + innerH / 2}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
          transform={`rotate(-90 13 ${M.top + innerH / 2})`}
        >
          Volatility (annualized)
        </text>

        {/* realized-vol line: the backward-looking series */}
        <g clipPath={`url(#${clipId})`}>
          <path
            d={realizedPath}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={1.8}
          />
          <circle cx={xTodayPx} cy={yScale(latestRealized)} r={3} fill="var(--accent)" />
        </g>

        {/* implied marker (forward) + premium bracket, or a degraded note */}
        {impliedAtmVol !== null ? (
          <>
            {/* forward projection of today's single implied observation */}
            <line
              x1={xTodayPx}
              x2={xScale(xForwardEnd)}
              y1={yScale(impliedAtmVol)}
              y2={yScale(impliedAtmVol)}
              stroke="var(--current)"
              strokeWidth={2}
              strokeLinecap="round"
            />
            <circle cx={xTodayPx} cy={yScale(impliedAtmVol)} r={3.4} fill="var(--current)" />
            <text
              x={xScale(xForwardEnd)}
              y={yScale(impliedAtmVol) - 7}
              textAnchor="end"
              fontSize="10.5"
              fill="var(--current)"
              className="num"
            >
              IV {(impliedAtmVol * 100).toFixed(1)}%
            </text>

            {/* premium bracket: the same-date gap, on the chart and labelled */}
            <line
              x1={xTodayPx}
              x2={xTodayPx}
              y1={yScale(latestRealized)}
              y2={yScale(impliedAtmVol)}
              stroke="var(--current)"
              strokeWidth={1}
            />
            <line
              x1={xTodayPx - 3}
              x2={xTodayPx + 3}
              y1={yScale(latestRealized)}
              y2={yScale(latestRealized)}
              stroke="var(--current)"
              strokeWidth={1}
            />
            <line
              x1={xTodayPx - 3}
              x2={xTodayPx + 3}
              y1={yScale(impliedAtmVol)}
              y2={yScale(impliedAtmVol)}
              stroke="var(--current)"
              strokeWidth={1}
            />
            <text
              x={xTodayPx - 8}
              y={(yScale(latestRealized) + yScale(impliedAtmVol)) / 2}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="10.5"
              fill="var(--current)"
              className="num"
            >
              premium {(premium ?? 0) >= 0 ? "+" : ""}
              {((premium ?? 0) * 100).toFixed(1)} pts
            </text>
          </>
        ) : (
          <text
            x={(xTodayPx + (M.left + innerW)) / 2}
            y={M.top + innerH / 2}
            textAnchor="middle"
            fontSize="11"
            fill="var(--muted)"
          >
            <tspan x={(xTodayPx + (M.left + innerW)) / 2} dy="0">
              ATM IV could not be
            </tspan>
            <tspan x={(xTodayPx + (M.left + innerW)) / 2} dy="14">
              solved for this expiry
            </tspan>
          </text>
        )}

        {/* the mandatory framing -- on the chart, one line, no interaction */}
        <text
          x={M.left + innerW / 2}
          y={H - 8}
          textAnchor="middle"
          fontSize="10.5"
          fill="var(--muted)"
        >
          {premiumNote}
        </text>
      </svg>

      {/* legend: distinguishes the backward series from the forward observation */}
      <div className="vc-legend">
        <span className="vc-legend-item">
          <span className="vc-swatch vc-swatch-line" />
          Realized vol — trailing {windowDays}d, ×√252 (backward)
        </span>
        <span className="vc-legend-item">
          <span className="vc-swatch vc-swatch-mark" />
          Implied vol — ATM-forward{impliedDaysToExpiry !== null
            ? `, ${impliedDaysToExpiry}d`
            : ""}{" "}
          (forward, today only)
        </span>
      </div>
    </div>
  );
}
