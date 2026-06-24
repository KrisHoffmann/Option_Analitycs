// Client-side position model and helpers. A UiLeg is the editable form of a
// leg; toLegInput maps it to the wire shape. Presets just pre-fill legs (the
// backend prices whatever legs it is sent), so the user can start from a
// recognizable structure and adjust.

import type { Instrument, LegInput, Side, SpotGridSpec } from "./types";

export interface UiLeg {
  id: string;
  instrument: Instrument;
  side: Side;
  quantity: number;
  strike: number;
  timeToExpiry: number; // years
}

// Deterministic ids (no Math.random / Date.now) so server and client render the
// same markup and hydration stays stable.
let legCounter = 0;
function nextId(): string {
  legCounter += 1;
  return `leg-${legCounter}`;
}

export function makeLeg(partial: Partial<UiLeg> = {}): UiLeg {
  return {
    id: nextId(),
    instrument: partial.instrument ?? "call",
    side: partial.side ?? "long",
    quantity: partial.quantity ?? 1,
    strike: partial.strike ?? 100,
    timeToExpiry: partial.timeToExpiry ?? 0.5,
  };
}

export function toLegInput(leg: UiLeg): LegInput {
  if (leg.instrument === "underlying") {
    return {
      instrument: "underlying",
      quantity: leg.quantity,
      side: leg.side,
      strike: null,
      time_to_expiry: null,
    };
  }
  return {
    instrument: leg.instrument,
    quantity: leg.quantity,
    side: leg.side,
    strike: leg.strike,
    time_to_expiry: leg.timeToExpiry,
  };
}

/** Unique option strikes in a position (for chart reference lines). */
export function optionStrikes(legs: UiLeg[]): number[] {
  const set = new Set<number>();
  for (const leg of legs) {
    if (leg.instrument !== "underlying") set.add(leg.strike);
  }
  return [...set].sort((a, b) => a - b);
}

/** A spot grid that frames the current spot and every strike, padded out. */
export function deriveGrid(spot: number, legs: UiLeg[]): SpotGridSpec {
  const refs = [spot, ...optionStrikes(legs)];
  const lo = Math.min(...refs);
  const hi = Math.max(...refs);
  const pad = Math.max(hi - lo, spot * 0.4, 1) * 0.6;
  return {
    spot_min: Math.max(0.01, lo - pad),
    spot_max: hi + pad,
    num_points: 121,
  };
}

const t = 0.5; // shared default expiry for presets (years)

export const PRESETS: { name: string; build: () => UiLeg[] }[] = [
  {
    name: "Bull call spread",
    build: () => [
      makeLeg({ instrument: "call", side: "long", strike: 95, timeToExpiry: t }),
      makeLeg({ instrument: "call", side: "short", strike: 105, timeToExpiry: t }),
    ],
  },
  {
    name: "Long straddle",
    build: () => [
      makeLeg({ instrument: "call", side: "long", strike: 100, timeToExpiry: t }),
      makeLeg({ instrument: "put", side: "long", strike: 100, timeToExpiry: t }),
    ],
  },
  {
    name: "Covered call",
    build: () => [
      makeLeg({ instrument: "underlying", side: "long", quantity: 1 }),
      makeLeg({ instrument: "call", side: "short", strike: 105, timeToExpiry: t }),
    ],
  },
  {
    name: "Iron condor",
    build: () => [
      makeLeg({ instrument: "put", side: "long", strike: 80, timeToExpiry: t }),
      makeLeg({ instrument: "put", side: "short", strike: 90, timeToExpiry: t }),
      makeLeg({ instrument: "call", side: "short", strike: 110, timeToExpiry: t }),
      makeLeg({ instrument: "call", side: "long", strike: 120, timeToExpiry: t }),
    ],
  },
];

export const INSTRUMENTS: { value: Instrument; label: string }[] = [
  { value: "call", label: "Call" },
  { value: "put", label: "Put" },
  { value: "underlying", label: "Underlying" },
];

export const SIDES: { value: Side; label: string }[] = [
  { value: "long", label: "Long" },
  { value: "short", label: "Short" },
];
