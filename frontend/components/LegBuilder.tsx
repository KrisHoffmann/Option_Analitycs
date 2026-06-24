"use client";

import type { Instrument, Side } from "@/lib/types";
import {
  INSTRUMENTS,
  PRESETS,
  SIDES,
  type UiLeg,
  makeLeg,
} from "@/lib/position";

interface LegBuilderProps {
  legs: UiLeg[];
  onChange: (legs: UiLeg[]) => void;
}

export default function LegBuilder({ legs, onChange }: LegBuilderProps) {
  function update(id: string, patch: Partial<UiLeg>) {
    onChange(legs.map((leg) => (leg.id === id ? { ...leg, ...patch } : leg)));
  }
  function remove(id: string) {
    onChange(legs.filter((leg) => leg.id !== id));
  }
  function add() {
    onChange([...legs, makeLeg()]);
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Position legs</h2>
        <button type="button" onClick={add} aria-label="Add a leg">
          + Add leg
        </button>
      </div>
      <div className="panel-body">
        <div className="preset-row" role="group" aria-label="Strategy presets">
          {PRESETS.map((preset) => (
            <button
              type="button"
              key={preset.name}
              onClick={() => onChange(preset.build())}
            >
              {preset.name}
            </button>
          ))}
        </div>

        {legs.length === 0 && (
          <p className="hint">
            No legs yet — add a leg or pick a preset above to build a position.
          </p>
        )}

        <div style={{ marginTop: 12 }}>
          {legs.map((leg, i) => {
            const isUnderlying = leg.instrument === "underlying";
            return (
              <div className="leg" key={leg.id}>
                <div className="leg-top">
                  <span className="leg-tag">Leg {i + 1}</span>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => remove(leg.id)}
                    aria-label={`Remove leg ${i + 1}`}
                  >
                    Remove
                  </button>
                </div>
                <div className="leg-grid">
                  <div className="field">
                    <label htmlFor={`${leg.id}-instrument`}>Instrument</label>
                    <select
                      id={`${leg.id}-instrument`}
                      value={leg.instrument}
                      onChange={(e) =>
                        update(leg.id, {
                          instrument: e.target.value as Instrument,
                        })
                      }
                    >
                      {INSTRUMENTS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor={`${leg.id}-side`}>Side</label>
                    <select
                      id={`${leg.id}-side`}
                      value={leg.side}
                      onChange={(e) =>
                        update(leg.id, { side: e.target.value as Side })
                      }
                    >
                      {SIDES.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor={`${leg.id}-qty`}>Quantity</label>
                    <input
                      id={`${leg.id}-qty`}
                      type="number"
                      min={0}
                      step={1}
                      value={leg.quantity}
                      onChange={(e) =>
                        update(leg.id, { quantity: Number(e.target.value) })
                      }
                    />
                  </div>
                  {!isUnderlying && (
                    <div className="field">
                      <label htmlFor={`${leg.id}-strike`}>
                        Strike <span className="unit">($)</span>
                      </label>
                      <input
                        id={`${leg.id}-strike`}
                        type="number"
                        min={0}
                        step={1}
                        value={leg.strike}
                        onChange={(e) =>
                          update(leg.id, { strike: Number(e.target.value) })
                        }
                      />
                    </div>
                  )}
                  {!isUnderlying && (
                    <div className="field span-2">
                      <label htmlFor={`${leg.id}-expiry`}>
                        Time to expiry <span className="unit">(years)</span>
                      </label>
                      <input
                        id={`${leg.id}-expiry`}
                        type="number"
                        min={0}
                        step={0.05}
                        value={leg.timeToExpiry}
                        onChange={(e) =>
                          update(leg.id, {
                            timeToExpiry: Number(e.target.value),
                          })
                        }
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
