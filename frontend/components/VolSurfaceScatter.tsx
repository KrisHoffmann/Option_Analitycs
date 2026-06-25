"use client";

import { useId, useMemo, useState } from "react";
import { niceTicks } from "@/lib/scale";
import { normalize, viridis } from "@/lib/viridis";
import type { VolSurface } from "@/lib/types";

interface FlatPoint {
  key: string;
  k: number; // forward log-moneyness
  t: number; // time to expiry (years)
  iv: number;
  optionType: string;
  strike: number;
  expiry: string;
}

interface VolSurfaceScatterProps {
  surface: VolSurface;
  ivMin: number;
  ivMax: number;
  kWindow: [number, number]; // central-density view window (forward log-moneyness)
}

// Honest scatter: x = forward log-moneyness k, y = TRUE time to expiry T (so the
// term structure is spaced by real calendar distance, not equal rows), colour =
// implied volatility on a single fixed scale. Gaps are absence of data -- nothing
// is interpolated and no surface is fitted between the points.
//
// The x-axis DEFAULTS to a data-driven window holding the central ~90% of points
// so the near-ATM smile stays legible; the liquid deep-OTM tail is never dropped
// (it is in the API response and the audit table) and is one expand-toggle away.
const W = 760;
const H = 460;
const M = { top: 18, right: 18, bottom: 70, left: 56 };

export default function VolSurfaceScatter({
  surface,
  ivMin,
  ivMax,
  kWindow,
}: VolSurfaceScatterProps) {
  const [hovered, setHovered] = useState<FlatPoint | null>(null);
  const [expanded, setExpanded] = useState(false);
  const clipId = useId();

  const points = useMemo<FlatPoint[]>(() => {
    const out: FlatPoint[] = [];
    for (const slice of surface.slices) {
      for (const p of slice.points) {
        out.push({
          key: `${slice.expiry}-${p.option_type}-${p.strike}`,
          k: p.log_moneyness,
          t: slice.time_to_expiry,
          iv: p.implied_volatility,
          optionType: p.option_type,
          strike: p.strike,
          expiry: slice.expiry,
        });
      }
    }
    return out;
  }, [surface]);

  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;

  const ks = points.map((p) => p.k);
  const kDataMin = Math.min(...ks, 0);
  const kDataMax = Math.max(...ks, 0);

  // Default domain = the central window (clamped into the data range); expanded
  // domain = the full data range. Either way the axis is labelled in TRUE k.
  const winLo = Math.max(kDataMin, kWindow[0]);
  const winHi = Math.min(kDataMax, kWindow[1]);
  const [domLo, domHi] = expanded ? [kDataMin, kDataMax] : [winLo, winHi];
  const xPad = (domHi - domLo) * 0.04 || 0.05;
  const xLo = domLo - xPad;
  const xHi = domHi + xPad;

  const tMax = Math.max(...points.map((p) => p.t), 0.1);
  const yLo = 0;
  const yHi = tMax * 1.05;

  const xScale = (v: number) => M.left + ((v - xLo) / (xHi - xLo)) * innerW;
  const yScale = (v: number) =>
    M.top + (1 - (v - yLo) / (yHi - yLo)) * innerH;

  const xTicks = niceTicks(xLo, xHi, 6).filter((t) => t >= xLo && t <= xHi);
  const yTicks = niceTicks(yLo, yHi, 5).filter((t) => t >= yLo && t <= yHi);

  // Points beyond the current view, for the truncation disclosure (only while
  // windowed -- expanding shows everything).
  const offLeft = expanded ? [] : points.filter((p) => p.k < domLo);
  const offRight = expanded ? [] : points.filter((p) => p.k > domHi);
  const offLeftMinK = offLeft.length ? Math.min(...offLeft.map((p) => p.k)) : 0;
  const offRightMaxK = offRight.length
    ? Math.max(...offRight.map((p) => p.k))
    : 0;

  const skewX = xScale(domLo) + 6;

  return (
    <div className="surf-chart">
      <div className="surf-chart-bar">
        <div className="surf-readout num" aria-live="polite">
          {hovered ? (
            <>
              <span
                className="surf-readout-iv"
                style={{
                  color: viridis(normalize(hovered.iv, ivMin, ivMax)),
                }}
              >
                IV {(hovered.iv * 100).toFixed(1)}%
              </span>
              <span>
                k {hovered.k >= 0 ? "+" : ""}
                {hovered.k.toFixed(3)}
              </span>
              <span>
                {hovered.optionType === "put" ? "put" : "call"} · K{" "}
                {hovered.strike}
              </span>
              <span>
                {Math.round(hovered.t * 365)}d · {hovered.expiry}
              </span>
            </>
          ) : (
            <span className="surf-readout-hint">
              Hover a point for its strike, expiry, and implied volatility.
            </span>
          )}
        </div>
        <button
          type="button"
          className="surf-toggle"
          aria-pressed={expanded}
          onClick={() => setExpanded((e) => !e)}
        >
          {expanded ? "Focus central range" : "Expand to full range"}
        </button>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        width="100%"
        role="img"
        aria-label={`Implied-volatility surface for ${surface.ticker}: ${points.length} contracts plotted by forward log-moneyness (horizontal) and time to expiry (vertical), coloured by implied volatility from ${(ivMin * 100).toFixed(0)}% to ${(ivMax * 100).toFixed(0)}%. ${expanded ? "Showing the full moneyness range." : `Showing the central range; ${offLeft.length + offRight.length} liquid points lie in the deeper wings.`}`}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={M.left} y={M.top} width={innerW} height={innerH} />
          </clipPath>
        </defs>

        {/* y grid + ticks (true time to expiry) */}
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
              {t.toFixed(2)}
            </text>
          </g>
        ))}

        {/* x ticks (forward log-moneyness, true k) */}
        {xTicks.map((t) => (
          <g key={`x${t}`}>
            <line
              x1={xScale(t)}
              x2={xScale(t)}
              y1={M.top}
              y2={M.top + innerH}
              stroke="var(--grid)"
              strokeWidth={1}
            />
            <text
              x={xScale(t)}
              y={M.top + innerH + 16}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted-2)"
              className="num"
            >
              {t > 0 ? "+" : ""}
              {t.toFixed(2)}
            </text>
          </g>
        ))}

        {/* ATM-forward reference line at k = 0 (only when in view) */}
        {xLo <= 0 && xHi >= 0 && (
          <>
            <line
              x1={xScale(0)}
              x2={xScale(0)}
              y1={M.top}
              y2={M.top + innerH}
              stroke="var(--zero-line)"
              strokeWidth={1.2}
              strokeDasharray="4 3"
            />
            <text x={xScale(0) + 4} y={M.top + 11} fontSize="9.5" fill="var(--muted)">
              ATM forward · k = 0
            </text>
          </>
        )}

        {/* axis titles */}
        <text
          x={M.left + innerW / 2}
          y={H - 30}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
        >
          Forward log-moneyness · k = ln(K / F)
        </text>
        <text
          x={14}
          y={M.top + innerH / 2}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
          transform={`rotate(-90 14 ${M.top + innerH / 2})`}
        >
          Time to expiry (years)
        </text>

        {/* downside-skew annotation, anchored to the left of the view */}
        <text x={skewX} y={M.top + innerH * 0.42} fontSize="9.5" fill="var(--muted)">
          ◂ put wing: IV climbs into
        </text>
        <text x={skewX} y={M.top + innerH * 0.42 + 12} fontSize="9.5" fill="var(--muted)">
          downside strikes (skew)
        </text>

        {/* coverage-asymmetry annotation on the upside */}
        {domHi > 0.02 && (
          <>
            <text
              x={xScale(domHi)}
              y={M.top + innerH * 0.16}
              textAnchor="end"
              fontSize="9.5"
              fill="var(--muted)"
            >
              calls thin out — far-OTM
            </text>
            <text
              x={xScale(domHi)}
              y={M.top + innerH * 0.16 + 12}
              textAnchor="end"
              fontSize="9.5"
              fill="var(--muted)"
            >
              index calls lack two-sided markets
            </text>
          </>
        )}

        {/* the points, clipped to the plot area */}
        <g clipPath={`url(#${clipId})`}>
          {points.map((p) => {
            const isHover = hovered?.key === p.key;
            return (
              <circle
                key={p.key}
                cx={xScale(p.k)}
                cy={yScale(p.t)}
                r={isHover ? 5 : 3.6}
                fill={viridis(normalize(p.iv, ivMin, ivMax))}
                stroke={isHover ? "var(--ink)" : "rgba(15,23,42,0.35)"}
                strokeWidth={isHover ? 1.4 : 0.6}
                opacity={0.92}
                onMouseEnter={() => setHovered(p)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: "pointer" }}
              >
                <title>
                  {`${p.optionType} K${p.strike} · ${p.expiry} · k=${p.k.toFixed(3)} · IV ${(p.iv * 100).toFixed(1)}%`}
                </title>
              </circle>
            );
          })}
        </g>

        {/* truncation disclosure at the edges -- the data exists, it is off-view */}
        {offLeft.length > 0 && (
          <text
            x={M.left + 2}
            y={M.top + innerH - 6}
            fontSize="9.5"
            fill="var(--accent)"
            className="num"
          >
            ◂ +{offLeft.length} liquid pts to k={offLeftMinK.toFixed(2)}
          </text>
        )}
        {offRight.length > 0 && (
          <text
            x={M.left + innerW - 2}
            y={M.top + innerH - 6}
            textAnchor="end"
            fontSize="9.5"
            fill="var(--accent)"
            className="num"
          >
            +{offRight.length} liquid pts to k=+{offRightMaxK.toFixed(2)} ▸
          </text>
        )}
      </svg>
    </div>
  );
}
