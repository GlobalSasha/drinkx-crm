"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { LeadOut, Stage } from "@/lib/types";

const PRIORITY_STYLES: Record<string, string> = {
  A: "bg-accent/10 text-accent",
  B: "bg-success/10 text-success",
  C: "bg-warning/10 text-warning",
  D: "bg-black/5 text-muted",
};

interface Props {
  stages: Stage[];
  leads: LeadOut[];
}

/**
 * Mobile fallback for /pipeline. Touch drag-drop is out of scope; this
 * is a read-only flat list grouped by stage. PipelineHeader still
 * renders above (search bar + "+ Лид" stay visible) — this component
 * only owns the body.
 */
export function PipelineList({ stages, leads }: Props) {
  const grouped = useMemo(() => {
    const m: Record<string, LeadOut[]> = {};
    stages.forEach((s) => (m[s.id] = []));
    leads.forEach((lead) => {
      const sid = lead.stage_id;
      if (sid && m[sid] !== undefined) {
        m[sid].push(lead);
      } else if (stages[0]) {
        // Unknown stage_id (fallback IDs path) — group under first stage
        // so the lead is still visible.
        m[stages[0].id].push(lead);
      }
    });
    return m;
  }, [stages, leads]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3">
      {stages.map((stage) => {
        const stageLeads = grouped[stage.id] ?? [];
        if (stageLeads.length === 0) return null;
        return (
          <section key={stage.id} className="mb-5">
            <div className="flex items-center gap-2 mb-2">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: stage.color }}
              />
              <h3 className="text-[11px] font-bold uppercase tracking-[0.15em] text-ink truncate">
                {stage.name}
              </h3>
              <span className="font-mono text-[10px] text-muted-2 tabular-nums">
                {stageLeads.length}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              {stageLeads.map((lead) => {
                const segCity = [lead.segment, lead.city].filter(Boolean).join(", ");
                return (
                  <Link
                    key={lead.id}
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    href={`/leads/${lead.id}` as any}
                    className="flex items-center gap-3 px-3 py-2.5 bg-white border border-black/5 rounded-xl active:bg-canvas hover:border-accent/30 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-ink truncate">
                        {lead.company_name}
                      </p>
                      {segCity && (
                        <p className="font-mono text-[10px] text-muted-2 mt-0.5 truncate lowercase">
                          {segCity}
                        </p>
                      )}
                    </div>
                    {lead.priority && (
                      <span
                        className={`shrink-0 font-mono text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
                          PRIORITY_STYLES[lead.priority] ?? "bg-black/5 text-muted"
                        }`}
                      >
                        {lead.priority}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}

      {leads.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-sm text-muted-2">Ни одной карточки в воронке</p>
        </div>
      )}
    </div>
  );
}
