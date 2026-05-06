"use client";
import { useState } from "react";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import type { LeadOut } from "@/lib/types";
import { DEFAULT_SCORING_CRITERIA, tierFromScore } from "@/lib/types";

const TIER_COLORS: Record<string, string> = {
  A: "bg-accent text-white",
  B: "bg-success text-white",
  C: "bg-warning text-white",
  D: "bg-muted text-white",
};

interface Props {
  lead: LeadOut;
}

export function ScoringTab({ lead }: Props) {
  const updateLead = useUpdateLead(lead.id);

  // Initialize sliders at 0 (no per-criterion storage in backend yet)
  const [values, setValues] = useState<number[]>(
    DEFAULT_SCORING_CRITERIA.map(() => 0)
  );

  // Compute total score: Σ((value/max_value) * weight)
  const total = Math.round(
    DEFAULT_SCORING_CRITERIA.reduce((sum, criterion, i) => {
      return sum + (values[i] / criterion.max_value) * criterion.weight;
    }, 0)
  );

  const tier = tierFromScore(total);

  function setValue(i: number, v: number) {
    setValues((prev) => {
      const next = [...prev];
      next[i] = v;
      return next;
    });
  }

  function handleSave() {
    updateLead.mutate({ score: total });
  }

  return (
    <div className="space-y-5">
      {/* Total score header */}
      <div className="flex items-center gap-4 bg-canvas rounded-2xl p-4">
        <div className="text-center">
          <p className="font-mono text-3xl font-bold text-ink">{total}</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-3 mt-0.5">
            Итог
          </p>
        </div>
        <div>
          <span
            className={`text-2xl font-extrabold px-4 py-2 rounded-2xl ${TIER_COLORS[tier]}`}
          >
            {tier}
          </span>
        </div>
        <div className="ml-auto text-right">
          <p className="text-xs text-muted-2">
            Текущий score в CRM:{" "}
            <span className="font-mono font-bold text-ink">{lead.score}</span>
          </p>
        </div>
      </div>

      {/* Criteria sliders */}
      <div className="space-y-4">
        {DEFAULT_SCORING_CRITERIA.map((criterion, i) => {
          const pct = (values[i] / criterion.max_value) * 100;
          return (
            <div key={criterion.key}>
              <div className="flex items-center justify-between mb-1">
                <label className="text-sm font-medium text-ink">
                  {criterion.label}
                </label>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted">
                    {values[i]}/{criterion.max_value}
                  </span>
                  <span className="font-mono text-[10px] bg-black/5 text-muted px-1.5 py-0.5 rounded-md">
                    ×{criterion.weight}%
                  </span>
                </div>
              </div>
              <input
                type="range"
                min={0}
                max={criterion.max_value}
                step={1}
                value={values[i]}
                onChange={(e) => setValue(i, Number(e.target.value))}
                className="w-full accent-accent"
              />
              <div className="flex justify-between text-[9px] font-mono text-muted-3 mt-0.5">
                <span>0</span>
                <span>
                  вклад: {Math.round((values[i] / criterion.max_value) * criterion.weight)}
                </span>
                <span>{criterion.max_value}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Save button */}
      <div className="pt-2">
        <button
          onClick={handleSave}
          disabled={updateLead.isPending}
          className="w-full py-2.5 rounded-pill text-sm font-semibold bg-ink text-white hover:bg-ink/90 disabled:opacity-50 transition-all"
        >
          {updateLead.isPending ? "Сохранение..." : `Сохранить score = ${total}`}
        </button>
      </div>
    </div>
  );
}
