"use client";

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
}: SliderProps) {
  return (
    <div className="slider-row">
      <div className="slider-top">
        <label htmlFor={id}>
          {label} {unit && <span className="unit">{unit}</span>}
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
