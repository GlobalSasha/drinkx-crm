"use client";
import { Search } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

/**
 * Renders `ai_data.research_gaps` — "what the agent could not find".
 * Semantically distinct from `risk_signals`. If empty, returns null
 * (right column collapses the slot entirely per spec).
 */
export function ResearchGapsCard({ lead }: Props) {
  const gaps =
    ((lead.ai_data as Record<string, unknown> | undefined)?.[
      "research_gaps"
    ] as string | undefined) ?? "";
  if (!gaps || !gaps.trim()) return null;

  return (
    <section className="bg-white rounded-2xl border border-brand-border p-4">
      <header className="flex items-center gap-2 mb-2">
        <Search size={14} className={C.color.muted} />
        <h3 className={`type-card-title ${C.color.text}`}>
          Research gaps
        </h3>
      </header>
      <p className={`type-caption ${C.color.muted} leading-relaxed`}>{gaps}</p>
    </section>
  );
}
