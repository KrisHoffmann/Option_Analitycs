// Number formatting. The backend is the single source of truth for the values;
// this only controls *display* precision. The rule from the brief: 2-4 decimals
// max, never an 8-decimal delta, and tabular alignment (handled by the .num /
// .mono CSS using Fira Code with tnum).

/** A monetary / value figure: 2 decimals, grouped thousands. */
export function money(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** A Greek or ratio: fixed decimals (default 4), with a sign-aware caller. */
export function decimals(value: number, places = 4): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
}

/** Compact axis tick label: no decimals for whole-ish values, else one. */
export function axisTick(value: number): string {
  const rounded = Math.round(value);
  if (Math.abs(value - rounded) < 0.5) return rounded.toLocaleString("en-US");
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}
