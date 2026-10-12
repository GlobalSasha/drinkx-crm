"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { C } from "@/lib/design-system";
import { useState } from "react";
import { useClaimLead } from "@/lib/hooks/use-leads";
import { segmentLabel } from "@/lib/i18n";
import type { LeadOut } from "@/lib/types";

/** Free lead preview: no editing, AI actions, feed or attachment queries. */
export function PoolLeadPreview({ lead }: { lead: LeadOut }) {
  const claim = useClaimLead();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const fields = [
    ["Город", lead.city],
    ["Сегмент", lead.segment ? segmentLabel(lead.segment) : null],
    ["Email", lead.email],
    ["Телефон", lead.phone],
    ["ИНН", lead.inn],
    ["Следующий шаг", lead.next_step],
  ];
  return (
    <div className="p-4 md:p-6 space-y-4">
      <Link href="/leads-pool" className="text-sm text-brand-accent-text hover:underline">← База лидов</Link>
      <div className="bg-white rounded-card border border-brand-border p-6 space-y-4">
        <h1 className="type-page-title break-words">{lead.company_name}</h1>
        <p className="text-sm text-brand-muted">Свободный лид. Возьмите его себе, чтобы работать с карточкой.</p>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {fields.map(([label, value]) => <div key={label}>
            <dt className="type-label text-brand-muted">{label}</dt>
            <dd className="text-sm text-brand-primary break-words">{value || "—"}</dd>
          </div>)}
        </dl>
        <button
          type="button"
          disabled={claim.isPending}
          onClick={() => {
            setError(null);
            claim.mutate(lead.id, {
              onError: (err) => {
                if (err.status === 403 || err.status === 404) {
                  qc.invalidateQueries({ queryKey: ["me"] });
                  qc.invalidateQueries({ queryKey: ["lead", lead.id] });
                }
                setError(err.status === 409 || err.status === 404
                ? "Лид уже взят другим менеджером. Вернитесь в базу и выберите другой."
                : err.status === 403 ? "Доступ к базе отозван. Обратитесь к руководителю."
                : "Не удалось взять лид. Попробуйте ещё раз.");
              },
            });
          }}
          className={`${C.button.primary} min-h-12 px-6 py-3 text-sm disabled:opacity-50`}
        >{claim.isPending ? "Берём в работу…" : "Взять себе"}</button>
        {error && <p role="alert" className="text-sm text-rose">{error}</p>}
      </div>
    </div>
  );
}
