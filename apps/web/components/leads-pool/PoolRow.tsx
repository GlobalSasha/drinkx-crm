"use client";

import { useRouter } from "next/navigation";
import { Loader2, Globe } from "lucide-react";
import { NeedsReviewRow } from "@/components/leads-pool/NeedsReviewRow";
import { T } from "@/lib/design-system";
import { tierFromScore } from "@/lib/types";
import type { LeadOut } from "@/lib/types";
import { segmentLabel } from "@/lib/i18n";

interface Props {
  lead: LeadOut;
  onClaim: (id: string) => void;
  claiming: boolean;
}

// ---- Row component ----

export function PoolRow({ lead, onClaim, claiming }: Props) {
  const router = useRouter();
  const tier = tierFromScore(lead.score);
  const TIER_STYLE: Record<string, string> = {
    A: "bg-brand-soft text-brand-accent",
    B: "bg-success/10 text-success",
    C: "bg-warning/10 text-warning",
    D: "bg-black/5 text-brand-muted",
  };

  function openLead() {
    router.push(`/leads/${lead.id}`);
  }

  function handleClaim(e: React.MouseEvent) {
    // Stop propagation so the row click doesn't fire after the button click.
    e.stopPropagation();
    onClaim(lead.id);
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      openLead();
    }
  }

  return (
    <tr
      role="link"
      tabIndex={0}
      aria-label={`Открыть лид ${lead.company_name}`}
      onClick={openLead}
      onKeyDown={handleKey}
      className={`border-b border-brand-border transition-opacity duration-300 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-inset ${claiming ? "opacity-40" : "hover:bg-brand-bg"}`}
    >
      <td className="px-4 py-3">
        <p className="font-semibold text-sm text-brand-primary">{lead.company_name}</p>
        {(lead.city || lead.segment) && (
          <p className="md:hidden text-xs text-brand-muted mt-0.5">
            {[lead.city, lead.segment ? segmentLabel(lead.segment) : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
        {lead.source_form_name && (
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono text-brand-accent-text bg-brand-soft"
            title="Источник заявки"
          >
            <Globe size={9} aria-hidden />
            {lead.source_form_name}
          </span>
        )}
        {lead.needs_review && (
          <NeedsReviewRow lead={lead} />
        )}
      </td>
      <td className="hidden md:table-cell px-4 py-3 text-sm text-brand-muted">{lead.city ?? "—"}</td>
      <td className="hidden md:table-cell px-4 py-3 text-sm text-brand-muted">{lead.segment ? segmentLabel(lead.segment) : "—"}</td>
      <td className="px-4 py-3">
        <span className={`text-xs font-bold px-1.5 py-0.5 rounded-md ${TIER_STYLE[tier]}`}>
          {tier}
        </span>
      </td>
      <td className="hidden md:table-cell px-4 py-3 type-amount text-brand-muted">
        {lead.fit_score != null ? lead.fit_score : "—"}
      </td>
      <td className="hidden md:table-cell px-4 py-3">
        <span className={`${T.mono} bg-black/5 text-brand-muted px-1.5 py-0.5 rounded-md`}>
          {lead.assignment_status}
        </span>
      </td>
      <td className="px-4 py-3 text-right whitespace-nowrap">
        {claiming ? (
          <span className="inline-flex items-center gap-1 text-xs text-brand-muted font-semibold">
            <Loader2 size={12} className="animate-spin" /> Взято
          </span>
        ) : (
          <button
            onClick={handleClaim}
            className="inline-flex items-center gap-1.5 bg-brand-accent text-white rounded-full px-3 py-1.5 text-xs font-semibold transition duration-200 hover:bg-brand-accent/90 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
          >
            Взять в работу
          </button>
        )}
      </td>
    </tr>
  );
}
