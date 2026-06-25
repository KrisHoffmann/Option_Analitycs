"use client";

import { useId, useMemo, useState } from "react";
import { niceTicks } from "@/lib/scale";
import { normalize, viridis } from "@/lib/viridis";
import type { VolSurface } from "@/lib/types";

interface SmileSlicesProps {
  surface: VolSurface;
  kWindow: [number, number]; // shared central-density view window
}

// IV (y) versus forward log-moneyness k (x), one line per selected expiry. A
// colour scatter encodes skew as a faint gradient; drawn as explicit smile
// curves the skew shape -- IV rising into low-k downside strikes -- is
// unmistakable. Same /vol-surface data, no extra request. Each expiry's colour
// is its position on the same viridis ramp used by the surface, so nearer (cool)
// and farther (warm) expiries are ordered by colour. The x-axis uses the same
// data-driven window as the surface (expandable), so short and long expiries --
// which reach very different depths -- stay legible together.
const W = 760;
const H = 420;
const M = { top: 18, right: 18, bottom: 56, left: 52 };
// Below this forward log-moneyness the deep-put tail is thinly quoted; the smile
// there is suggestive, not precise. We band it rather than imply tail accuracy.
const DEEP_PUT_K = -0.4;

/** Pick up to four expiries spread across the term for a legible default. */
function defaultSelection(count: number): number[] {
  if (count <= 4) return Array.from({ length: count }, (_, i) => i);
  return [
    0,
    Math.round((count - 1) / 3),
    Math.round((2 * (count - 1)) / 3),
    count - 1,
  ].filter((v, i, a) => a.indexOf(v) === i);
}

export default function SmileSlices({ surface, kWindow }: SmileSlicesProps) {
  const clipId = useId();
  const withPoints = useMemo(
    () => surface.slices.filter((s) => s.points.length > 1),
    [surface],
  );
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(defaultSelection(withPoints.length)),
  );
  const [expanded, setExpanded] = useState(false);

  const tValues = withPoints.map((s) => s.time_to_expiry);
  const tMin = Math.min(...tValues, 0);
  const tMax = Math.max(...tValues, 0.1);
  const colorFor = (t: number) => viridis(normalize(t, tMin, tMax));

  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;

  const shown = withPoints.filter((_, i) => selected.has(i));
  const allPts = shown.flatMap((s) => s.points);

  const ks = allPts.map((p) => p.log_moneyness);
  const ivs = allPts.map((p) => p.implied_volatility);
  const kDataMin = Math.min(...ks, 0);
  const kDataMax = Math.max(...ks, 0);

  // Same windowing contract as the surface scatter: focus the central range by
  // default, full range one toggle away. Axis is labelled in true k either way.
  const winLo = Math.max(kDataMin, kWindow[0]);
  const winHi = Math.min(kDataMax, kWindow[1]);
  const [domLo, domHi] = expanded ? [kDataMin, kDataMax] : [winLo, winHi];
  const kPad = (domHi - domLo) * 0.04 || 0.05;
  const xLo = domLo - kPad;
  const xHi = domHi + kPad;

  const ivLo = Math.min(...ivs);
  const ivHi = Math.max(...ivs);
  const ivPad = (ivHi - ivLo) * 0.12 || 0.02;
  const yLo = Math.max(0, ivLo - ivPad);
  const yHi = ivHi + ivPad;

  const xScale = (v: number) => M.left + ((v - xLo) / (xHi - xLo)) * innerW;
  const yScale = (v: number) =>
    M.top + (1 - (v - yLo) / (yHi - yLo)) * innerH;

  const xTicks = niceTicks(xLo, xHi, 6).filter((t) => t >= xLo && t <= xHi);
  const yTicks = niceTicks(yLo, yHi, 5).filter((t) => t >= yLo && t <= yHi);

  const toggle = (i: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  // Deep-put caution band, clamped to the visible window.
  const showDeepBand = xLo < DEEP_PUT_K;
  const deepBandRight = xScale(Math.max(xLo, Math.min(DEEP_PUT_K, xHi)));

  // Off-window disclosure among the SELECTED expiries.
  const offLeft = expanded ? [] : allPts.filter((p) => p.log_moneyness < domLo);
  const offLeftMinK = offLeft.length
    ? Math.min(...offLeft.map((p) => p.log_moneyness))
    : 0;

  return (
    <div className="surf-chart">
      <div className="surf-chart-bar">
        <div className="surf-slice-chips">
          {withPoints.map((s, i) => {
            const on = selected.has(i);
            return (
              <button
                key={s.expiry}
                type="button"
                className={`surf-chip${on ? " on" : ""}`}
                aria-pressed={on}
                onClick={() => toggle(i)}
              >
                <span
                  className="surf-chip-dot"
                  style={{
                    background: on
                      ? colorFor(s.time_to_expiry)
                      : "var(--border-strong)",
                  }}
                />
                {Math.round(s.time_to_expiry * 365)}d
              </button>
            );
          })}
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
        aria-label={`Implied-volatility smiles for ${shown.length} selected expiries of ${surface.ticker}, plotted as IV against forward log-moneyness.${offLeft.length ? ` ${offLeft.length} deeper points are off the focused view.` : ""}`}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={M.left} y={M.top} width={innerW} height={innerH} />
          </clipPath>
        </defs>

        {/* deep-put-tail caution band (k < -0.4): thinly quoted, low precision */}
        {showDeepBand && (
          <>
            <rect
              x={M.left}
              y={M.top}
              width={Math.max(0, deepBandRight - M.left)}
              height={innerH}
              fill="rgba(180,83,9,0.06)"
            />
            <text x={M.left + 4} y={M.top + innerH - 6} fontSize="9" fill="var(--current)">
              k &lt; −0.4: thinly quoted, low precision
            </text>
          </>
        )}

        {/* y grid + ticks (IV) */}
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

        {/* x ticks (forward log-moneyness, true k) */}
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
            {t > 0 ? "+" : ""}
            {t.toFixed(2)}
          </text>
        ))}

        {/* k = 0 reference (only when in view) */}
        {xLo <= 0 && xHi >= 0 && (
          <line
            x1={xScale(0)}
            x2={xScale(0)}
            y1={M.top}
            y2={M.top + innerH}
            stroke="var(--zero-line)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        )}

        {/* axis titles */}
        <text
          x={M.left + innerW / 2}
          y={H - 18}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
        >
          Forward log-moneyness · k = ln(K / F)
        </text>
        <text
          x={13}
          y={M.top + innerH / 2}
          textAnchor="middle"
          fontSize="11"
          fill="var(--muted)"
          transform={`rotate(-90 13 ${M.top + innerH / 2})`}
        >
          Implied volatility
        </text>

        {/* one smile curve per selected expiry, clipped to the plot area */}
        <g clipPath={`url(#${clipId})`}>
          {shown.map((s) => {
            const sorted = [...s.points].sort(
              (a, b) => a.log_moneyness - b.log_moneyness,
            );
            const color = colorFor(s.time_to_expiry);
            const path = sorted
              .map(
                (p, i) =>
                  `${i === 0 ? "M" : "L"}${xScale(p.log_moneyness)},${yScale(p.implied_volatility)}`,
              )
              .join(" ");
            return (
              <g key={s.expiry}>
                <path d={path} fill="none" stroke={color} strokeWidth={1.6} opacity={0.9} />
                {sorted.map((p) => (
                  <circle
                    key={p.strike}
                    cx={xScale(p.log_moneyness)}
                    cy={yScale(p.implied_volatility)}
                    r={2.4}
                    fill={color}
                    stroke="rgba(15,23,42,0.3)"
                    strokeWidth={0.5}
                  >
                    <title>
                      {`${Math.round(s.time_to_expiry * 365)}d · ${p.option_type} K${p.strike} · k=${p.log_moneyness.toFixed(3)} · IV ${(p.implied_volatility * 100).toFixed(1)}%`}
                    </title>
                  </circle>
                ))}
              </g>
            );
          })}
        </g>

        {/* truncation disclosure -- the deeper points exist, off the focused view */}
        {offLeft.length > 0 && (
          <text
            x={M.left + 2}
            y={M.top + 12}
            fontSize="9.5"
            fill="var(--accent)"
            className="num"
          >
            ◂ +{offLeft.length} pts to k={offLeftMinK.toFixed(2)}
          </text>
        )}
      </svg>
    </div>
  );
}
