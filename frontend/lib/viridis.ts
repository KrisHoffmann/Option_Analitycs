// A perceptually-uniform sequential colour scale (matplotlib's "viridis"),
// used to encode implied volatility on the surface. Chosen over a blue->red
// gradient on purpose: viridis is colourblind-safe and monotonic in lightness,
// so the ordering of values survives most colour-vision deficiencies. Colour is
// never the only encoding here -- every point also carries its numeric IV, and
// the chart ships a labelled legend -- but the scale itself should still be
// honest about ordering.

// Ten evenly-spaced stops sampled from viridis (t = 0.0 .. 1.0).
const STOPS: [number, number, number][] = [
  [68, 1, 84], // 0.0  dark violet (low IV)
  [72, 40, 120], // 0.1
  [62, 73, 137], // 0.2
  [49, 104, 142], // 0.3
  [38, 130, 142], // 0.4
  [31, 158, 137], // 0.5
  [53, 183, 121], // 0.6
  [109, 205, 89], // 0.7
  [180, 222, 44], // 0.8
  [253, 231, 37], // 1.0  yellow (high IV)
];

/** viridis colour for t in [0, 1], clamped, as an `rgb(...)` string. */
export function viridis(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const scaled = clamped * (STOPS.length - 1);
  const i = Math.min(Math.floor(scaled), STOPS.length - 2);
  const f = scaled - i;
  const [r1, g1, b1] = STOPS[i];
  const [r2, g2, b2] = STOPS[i + 1];
  const r = Math.round(r1 + (r2 - r1) * f);
  const g = Math.round(g1 + (g2 - g1) * f);
  const b = Math.round(b1 + (b2 - b1) * f);
  return `rgb(${r}, ${g}, ${b})`;
}

/** Maps a value onto [0, 1] within [min, max] (a degenerate range -> 0.5). */
export function normalize(value: number, min: number, max: number): number {
  if (max <= min) return 0.5;
  return (value - min) / (max - min);
}
