"use client";

import { useState } from "react";
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
  const [confirmingDismiss, setConfirmingDismiss] = useState(false);
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

  // Cross-guard: either mutation in flight disables both action buttons,
  // preventing a race between «Подтвердить» (clear needs_review) and «Не лид»
  // (soft-delete) on the same lead — security-auditor finding LOW.
  const busy = confirm.isPending || dismiss.isPending;

  return (
    <div className="mt-1 flex items-center gap-2 flex-wrap">
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono text-warning bg-warning/10 border border-warning/20"
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
        disabled={busy}
        className="text-xs px-2 py-0.5 rounded bg-success text-white hover:bg-success/90 disabled:opacity-50"
      >
        Подтвердить
      </button>
      {confirmingDismiss ? (
        <span className="inline-flex items-center gap-1.5 text-xs">
          <span className="text-brand-muted">Точно не лид?</span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              dismiss.mutate();
            }}
            disabled={busy}
            className="px-2 py-0.5 rounded text-rose bg-rose/10 hover:bg-rose/15 font-semibold disabled:opacity-50"
          >
            Да, удалить
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setConfirmingDismiss(false);
            }}
            disabled={busy}
            className="px-2 py-0.5 rounded text-brand-muted hover:bg-brand-panel disabled:opacity-50"
          >
            Отмена
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setConfirmingDismiss(true);
          }}
          disabled={busy}
          className="text-xs px-2 py-0.5 rounded text-rose bg-rose/10 hover:bg-rose/15 disabled:opacity-50"
        >
          Не лид
        </button>
      )}
    </div>
  );
}
