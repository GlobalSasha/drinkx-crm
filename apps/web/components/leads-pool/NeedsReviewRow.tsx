"use client";

import { Sparkles } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { LeadOut } from "@/lib/types";

interface Props {
  lead: LeadOut;
}

/**
 * Sprint 3.7 G4 — pill + two-button tray surfaced on leads with
 * `needs_review=true`. «Подтвердить» clears the flag; «Не лид» soft-deletes
 * the lead by setting assignment_status to "deleted".
 */
export function NeedsReviewRow({ lead }: Props) {
  const qc = useQueryClient();
  const confidence = Number(
    (lead.ai_data as Record<string, unknown> | null)?.auto_create_confidence ?? 0,
  );
  const percent = Math.round(confidence * 100);

  const confirm = useMutation({
    mutationFn: () =>
      api.patch(`/leads/${lead.id}`, { needs_review: false }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });

  const dismiss = useMutation({
    mutationFn: () =>
      api.patch(`/leads/${lead.id}`, { assignment_status: "deleted" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });

  return (
    <div className="mt-1 flex items-center gap-2 flex-wrap">
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-amber-700 bg-amber-50 border border-amber-200"
        title="AI создал этого лида автоматически из входящего письма"
      >
        <Sparkles size={10} aria-hidden />
        AI создал · {percent}%
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          confirm.mutate();
        }}
        disabled={confirm.isPending}
        className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        Подтвердить
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          if (window.confirm("Удалить этого лида? AI ошибся — он не похож на B2B-обращение.")) {
            dismiss.mutate();
          }
        }}
        disabled={dismiss.isPending}
        className="text-[11px] px-2 py-0.5 rounded text-rose-700 bg-rose-50 hover:bg-rose-100 disabled:opacity-50"
      >
        Не лид
      </button>
    </div>
  );
}
