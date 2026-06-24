"use client";

import { useEffect, useRef, useState } from "react";
import { axisTick, money } from "@/lib/format";

interface PayoffChartProps {
  spots: number[];
  payoff: number[];
  currentValue: number[];
  strikes: number[];
  currentSpot: number;
}

const HEIGHT = 380;
const M = { top: 16, right: 18, bottom: 44, left: 64 };

/** "Nice" evenly-spaced tick values across [min, max]. */
function niceTicks(min: number, max: number, count: number): number[] {
  if (min === max) return [min];
  const range = niceNum(max - min, false);
  const step = niceNum(range / (count - 1), true);
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= max + step * 1e-6; v += step) {
    ticks.push(Math.abs(v) < step * 1e-6 ? 0 : v);
  }
  return ticks;
}
function niceNum(range: number, round: boolean): number {
  const exp = Math.floor(Math.log10(range));
  const frac = range / 10 ** exp;
  let nice: number;
  if (round) nice = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;
  else nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  return nice * 10 ** exp;
}

export default function PayoffChart({
  spots,
  payoff,
  currentValue,
  strikes,
  currentSpot,
}: PayoffChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(680);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const innerW = Math.max(width - M.left - M.right, 10);
  const innerH = HEIGHT - M.top - M.bottom;

  const xMin = spots[0];
  const xMax = spots[spots.length - 1];

  // y-domain ALWAYS includes 0 -- the payoff baseline is never truncated.
  const allY = [...payoff, ...currentValue];
  const dataMin = Math.min(...allY);
  const dataMax = Math.max(...allY);
  const yLo = Math.min(0, dataMin);
  const yHi = Math.max(0, dataMax);
  const pad = (yHi - yLo) * 0.08 || 1;
  const yMin = yLo - pad;
  const yMax = yHi + pad;

  const xScale = (v: number) => M.left + ((v - xMin) / (xMax - xMin)) * innerW;
  const yScale = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin)) * innerH;

  const linePath = (ys: number[]) =>
    ys
      .map((y, i) => `${i === 0 ? "M" : "L"}${xScale(spots[i])},${yScale(y)}`)
      .join(" ");

  const xTicks = niceTicks(xMin, xMax, 7).filter((t) => t >= xMin && t <= xMax);
  const yTicks = niceTicks(yMin, yMax, 6);

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const frac = Math.min(Math.max(x / innerW, 0), 1);
    setHoverIndex(Math.round(frac * (spots.length - 1)));
  }

  const hover = hoverIndex !== null ? hoverIndex : null;

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`Payoff-at-expiry and current model value of the position across underlying prices from ${money(
          xMin,
        )} to ${money(xMax)}.`}
      >
        {/* horizontal gridlines + y-axis (position value) */}
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line
              x1={M.left}
              x2={M.left + innerW}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke={t === 0 ? "var(--zero-line)" : "var(--grid)"}
              strokeWidth={t === 0 ? 1.5 : 1}
            />
            <text
              x={M.left - 8}
              y={yScale(t)}
              textAnchor="end"
              dominantBaseline="central"
              fontSize="11"
              fill="var(--muted)"
              className="num"
            >
              {axisTick(t)}
            </text>
          </g>
        ))}

        {/* strike reference lines */}
        {strikes.map((k) => (
          <g key={`k${k}`}>
            <line
              x1={xScale(k)}
              x2={xScale(k)}
              y1={M.top}
              y2={M.top + innerH}
              stroke="var(--strike-line)"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
            <text
              x={xScale(k)}
              y={M.top + 2}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted-2)"
              className="num"
            >
              K {axisTick(k)}
            </text>
          </g>
        ))}

        {/* current spot marker */}
        <line
          x1={xScale(currentSpot)}
          x2={xScale(currentSpot)}
          y1={M.top}
          y2={M.top + innerH}
          stroke="var(--spot-line)"
          strokeWidth={1.25}
        />
        <text
          x={xScale(currentSpot)}
          y={M.top + innerH + 26}
          textAnchor="middle"
          fontSize="10"
          fill="var(--ink)"
          className="num"
        >
          spot {axisTick(currentSpot)}
        </text>

        {/* x-axis ticks (underlying price) */}
        {xTicks.map((t) => (
          <text
            key={`x${t}`}
            x={xScale(t)}
            y={M.top + innerH + 16}
            textAnchor="middle"
            fontSize="11"
            fill="var(--muted)"
            className="num"
          >
            {axisTick(t)}
          </text>
        ))}

        {/* current-value curve (amber, dashed) then payoff (blue, solid) on top */}
        <path
          d={linePath(currentValue)}
          fill="none"
          stroke="var(--current)"
          strokeWidth={2}
          strokeDasharray="5 4"
        />
        <path
          d={linePath(payoff)}
          fill="none"
          stroke="var(--payoff)"
          strokeWidth={2.25}
        />

        {/* axis titles */}
        <text
          x={M.left + innerW / 2}
          y={HEIGHT - 4}
          textAnchor="middle"
          fontSize="12"
          fill="var(--muted)"
        >
          Underlying price ($)
        </text>
        <text
          transform={`translate(14, ${M.top + innerH / 2}) rotate(-90)`}
          textAnchor="middle"
          fontSize="12"
          fill="var(--muted)"
        >
          Position value ($)
        </text>

        {/* hover crosshair + markers */}
        {hover !== null && (
          <g pointerEvents="none">
            <line
              x1={xScale(spots[hover])}
              x2={xScale(spots[hover])}
              y1={M.top}
              y2={M.top + innerH}
              stroke="var(--muted-2)"
              strokeWidth={1}
            />
            <circle cx={xScale(spots[hover])} cy={yScale(currentValue[hover])} r={3.5} fill="var(--current)" />
            <circle cx={xScale(spots[hover])} cy={yScale(payoff[hover])} r={3.5} fill="var(--payoff)" />
          </g>
        )}

        {/* interaction surface */}
        <rect
          x={M.left}
          y={M.top}
          width={innerW}
          height={innerH}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={() => setHoverIndex(null)}
        />
      </svg>

      {/* hover readout (text, so values are exact and selectable) */}
      <div className="hint num" style={{ minHeight: 18, paddingLeft: M.left }}>
        {hover !== null ? (
          <>
            At underlying {money(spots[hover])}: payoff-at-expiry{" "}
            {money(payoff[hover])} · current value {money(currentValue[hover])}
          </>
        ) : (
          <>Hover the chart to read values at a given underlying price.</>
        )}
      </div>
    </div>
  );
}
