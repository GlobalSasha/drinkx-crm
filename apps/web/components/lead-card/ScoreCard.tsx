"use client";
import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useUpdateLead } from "@/lib/hooks/use-lead";
import {
  DEFAULT_SCORING_CRITERIA,
  tierFromScore,
  type LeadOut,
} from "@/lib/types";
import { C } from "@/lib/design-system";
import { priorityChip } from "@/lib/ui/priority";

interface Props {
  lead: LeadOut;
}

/**
 * Collapsible "Оценка лида" card for the right column.
 *
 * Collapsed: shows current score / 100 + priority + DrinkX fit / 10.
 * Expanded: 4 weighted sliders that recompute the total; "Сохранить
 * оценку" persists to `lead.score`. Per RECON Section 7 the
 * per-criterion answers are not stored anywhere — only the total
 * survives.
 */
export function ScoreCard({ lead }: Props) {
  const [expanded, setExpanded] = useState(false);
  const updateLead = useUpdateLead(lead.id);
  // Sprint Lead Card Redesign — only the first four criteria appear in
  // the right-rail expanded panel (per spec). The full eight-criterion
  // editor is reachable via the «Все критерии» link inside the panel.
  const VISIBLE = DEFAULT_SCORING_CRITERIA.slice(0, 4);
  const [values, setValues] = useState<number[]>(VISIBLE.map(() => 0));

  const drinkxFit =
    (lead.ai_data as Record<string, unknown> | undefined)?.["drinkx_fit_score"];
  const drinkxFitDisplay =
    typeof drinkxFit === "number" ? drinkxFit : Number(lead.fit_score ?? 0) || 0;

  const totalSliders = Math.round(
    VISIBLE.reduce(
      (sum, c, i) => sum + (values[i] / c.max_value) * c.weight,
      0,
    ),
  );

  function setValue(i: number, v: number) {
    setValues((prev) => {
      const next = [...prev];
      next[i] = v;
      return next;
    });
  }

  function handleSave() {
    updateLead.mutate({ score: totalSliders });
  }

  return (
    <section className="bg-white rounded-2xl border border-brand-border p-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-3"
        aria-expanded={expanded}
      >
        <span className={`type-card-title ${C.color.text}`}>
          Оценка лида
        </span>
        <span className={`type-caption ${C.color.muted} font-mono`}>
          Score / Приоритет
        </span>
      </button>

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-1">
          <span className={`type-kpi-number ${C.color.text}`}>
            {lead.score ?? "—"}
          </span>
          <span className={`type-caption ${C.color.muted} font-mono`}>/100</span>
        </div>
        <div className="flex items-center gap-2">
          {lead.priority && (
            <span
              className={`type-caption font-semibold px-2 py-0.5 rounded-full ${priorityChip(lead.priority)}`}
            >
              {lead.priority}
            </span>
          )}
          <span className={`type-caption ${C.color.muted}`}>
            DrinkX fit {drinkxFitDisplay}/10
          </span>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="p-1 rounded-full hover:bg-brand-panel transition-colors"
            aria-label={expanded ? "Свернуть" : "Развернуть"}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3 pt-4 border-t border-brand-border">
          {VISIBLE.map((c, i) => (
            <div key={c.key}>
              <div className="flex items-center justify-between mb-1">
                <label className={`type-caption ${C.color.text}`}>{c.label}</label>
                <span className={`font-mono type-caption ${C.color.muted}`}>
                  {values[i]}/{c.max_value}
                  <span className="ml-1.5 bg-brand-panel px-1.5 py-0.5 rounded-md">
                    ×{c.weight}%
                  </span>
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={c.max_value}
                step={1}
                value={values[i]}
                onChange={(e) => setValue(i, Number(e.target.value))}
                className="w-full accent-brand-accent"
              />
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            <span className={`type-caption ${C.color.muted}`}>
              Итог: <span className={`font-mono font-bold ${C.color.text}`}>{totalSliders}</span> · {tierFromScore(totalSliders)}
            </span>
            <button
              type="button"
              onClick={handleSave}
              disabled={updateLead.isPending}
              className="px-3 py-1.5 type-body font-semibold bg-ink text-white rounded-full disabled:opacity-50 transition-opacity"
            >
              {updateLead.isPending ? "…" : "Сохранить оценку"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
