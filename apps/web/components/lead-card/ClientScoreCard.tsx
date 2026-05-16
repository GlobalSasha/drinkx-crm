"use client";

// Lead Card v2 — replaces the old «Оценка лида» card with a clickable
// «Оценка клиента» surface that opens an editable breakdown modal.
// The big AI «DrinkX fit X/10» line is gone (kept in DB; no longer
// shown here — see ResearchGapsCard / future AI surfaces).

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";
import { ScoreBreakdownModal } from "./ScoreBreakdownModal";

interface Props {
  lead: LeadOut;
}

function priorityPillStyle(letter: string | null | undefined): string {
  switch (letter) {
    case "A":
      return "bg-success/15 text-success";
    case "B":
      return "bg-success/10 text-success";
    case "C":
      return "bg-warning/10 text-warning";
    case "D":
      return "bg-black/5 text-brand-muted";
    default:
      return "bg-black/5 text-brand-muted";
  }
}

export function ClientScoreCard({ lead }: Props) {
  const [popupOpen, setPopupOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setPopupOpen(true)}
        aria-label="Открыть детализацию оценки"
        className="w-full text-left bg-white rounded-2xl border border-brand-border p-4 hover:border-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
      >
        <div className="flex items-center justify-between gap-3 mb-2">
          <span className={`type-card-title ${C.color.text}`}>
            Оценка клиента
          </span>
          <ChevronRight size={14} className="text-brand-muted" />
        </div>

        <div className="flex items-baseline gap-1 mb-2">
          <span className={`type-kpi-number ${C.color.text}`}>
            {lead.score ?? "—"}
          </span>
          <span className={`type-caption ${C.color.muted} font-mono`}>/100</span>
        </div>

        {(lead.priority_label || lead.priority) && (
          <span
            className={`inline-block type-caption font-semibold px-2.5 py-0.5 rounded-full ${priorityPillStyle(lead.priority)}`}
          >
            {lead.priority_label ?? lead.priority}
          </span>
        )}

        <p className={`type-caption ${C.color.mutedLight} mt-3`}>
          Кликни — посмотреть из чего собран балл →
        </p>
      </button>

      {popupOpen && (
        <ScoreBreakdownModal
          leadId={lead.id}
          onClose={() => setPopupOpen(false)}
        />
      )}
    </>
  );
}
