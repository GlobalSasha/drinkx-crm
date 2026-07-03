"use client";

import { T } from "@/lib/design-system";

interface Props {
  value: number;
  onChange: (v: number) => void;
}

// ---- Fit score slider ----

export function FitSlider({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className={`${T.mono} uppercase text-brand-muted whitespace-nowrap`}>
        Fit ≥ {value}
      </span>
      <input
        type="range"
        min={0}
        max={10}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-24 accent-accent"
      />
    </div>
  );
}
