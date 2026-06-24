// Small shared helpers for the hand-rolled SVG charts: "nice" axis ticks and a
// linear scale factory. Kept dependency-free and used by both the payoff chart
// and the Greek small-multiples so axis behaviour is identical everywhere.

/** "Nice" evenly-spaced tick values across [min, max]. */
export function niceTicks(min: number, max: number, count: number): number[] {
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

/** A y-domain that always includes zero, padded, so no curve sits against an
 *  exaggerating, truncated baseline. */
export function zeroAnchoredDomain(values: number[]): [number, number] {
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const pad = (hi - lo) * 0.08 || 1;
  return [lo - pad, hi + pad];
}
