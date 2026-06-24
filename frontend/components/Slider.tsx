"use client";

import type { GlossaryKey } from "@/lib/glossary";
import InfoTip from "./InfoTip";

interface SliderProps {
  id: string;
  label: string;
  unit?: string;
  min: number;
  max: number;
  step: number;
  value: number;
  display: string; // formatted current value
  onChange: (value: number) => void;
  infoKey?: GlossaryKey;
}

export default function Slider({
  id,
  label,
  unit,
  min,
  max,
  step,
  value,
  display,
  onChange,
  infoKey,
}: SliderProps) {
  return (
    <div className="slider-row">
      <div className="slider-top">
        <label htmlFor={id}>
          {label} {unit && <span className="unit">{unit}</span>}
          {infoKey && <InfoTip k={infoKey} />}
        </label>
        <span className="slider-value num">{display}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
