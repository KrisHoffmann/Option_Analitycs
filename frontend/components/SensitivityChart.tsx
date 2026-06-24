"use client";

import { axisTick } from "@/lib/format";
import { niceTicks, zeroAnchoredDomain } from "@/lib/scale";

interface SensitivityChartProps {
  title: string;
  unit: string;
  xLabel: string;
  xs: number[];
  ys: number[];
  markerX: number;
  markerY: number;
  valueText: string;
}

// Fixed internal coordinate system; scales to the grid cell via viewBox. No
// mouse interaction here -- the marker is driven by the sliders -- so a fixed
// viewBox keeps all small multiples identical and crisp.
const W = 320;
const H = 188;
const M = { top: 10, right: 12, bottom: 30, left: 46 };

export default function SensitivityChart({
  title,
  unit,
  xLabel,
  xs,
  ys,
  markerX,
  markerY,
  valueText,
}: SensitivityChartProps) {
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;

  const xMin = xs[0];
  const xMax = xs[xs.length - 1];
  // y-domain anchored at zero so a flat-looking Greek is not visually inflated.
  const [yMin, yMax] = zeroAnchoredDomain(ys);

  const xScale = (v: number) => M.left + ((v - xMin) / (xMax - xMin)) * innerW;
  const yScale = (v: number) =>
    M.top + (1 - (v - yMin) / (yMax - yMin)) * innerH;

  const path = ys
    .map((y, i) => `${i === 0 ? "M" : "L"}${xScale(xs[i])},${yScale(y)}`)
    .join(" ");

  const yTicks = niceTicks(yMin, yMax, 4);
  const xTicks = niceTicks(xMin, xMax, 4).filter((t) => t >= xMin && t <= xMax);
  const clampedMarkerX = Math.min(Math.max(markerX, xMin), xMax);

  return (
    <div className="sm-cell">
      <div className="sm-head">
        <div>
          <span className="sm-title">{title}</span>
          <span className="sm-unit">{unit}</span>
        </div>
        <span className="sm-value num">{valueText}</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        role="img"
        aria-label={`${title} versus ${xLabel}. Current value ${valueText}.`}
      >
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke={t === 0 ? "var(--zero-line)" : "var(--grid)"}
              strokeWidth={t === 0 ? 1.2 : 1}
            />
            <text
              x={M.left - 6}
              y={yScale(t)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="9.5"
              fill="var(--muted-2)"
              className="num"
            >
              {axisTick(t)}
            </text>
          </g>
        ))}

        {xTicks.map((t) => (
          <text
            key={`x${t}`}
            x={xScale(t)}
            y={M.top + innerH + 13}
            textAnchor="middle"
            fontSize="9.5"
            fill="var(--muted-2)"
            className="num"
          >
            {axisTick(t)}
          </text>
        ))}
        <text
          x={M.left + innerW / 2}
          y={H - 2}
          textAnchor="middle"
          fontSize="10"
          fill="var(--muted)"
        >
          {xLabel}
        </text>

        <path d={path} fill="none" stroke="var(--payoff)" strokeWidth={2} />

        {/* current-point marker (amber) at the swept-variable's slider value */}
        <line
          x1={xScale(clampedMarkerX)}
          x2={xScale(clampedMarkerX)}
          y1={M.top}
          y2={M.top + innerH}
          stroke="var(--current)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <circle
          cx={xScale(clampedMarkerX)}
          cy={yScale(markerY)}
          r={3.5}
          fill="var(--current)"
        />
      </svg>
    </div>
  );
}
