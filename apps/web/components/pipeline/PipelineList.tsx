"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { LeadOut, Stage } from "@/lib/types";
import { priorityChip } from "@/lib/ui/priority";
import { T } from "@/lib/design-system";

interface Props {
  stages: Stage[];
  leads: LeadOut[];
}

/**
 * Mobile fallback for /pipeline. Touch drag-drop is out of scope; this
 * is a read-only flat list grouped by stage. PipelineHeader still
 * renders above (search bar + "+ Лид" stay visible) — this component
 * only owns the body.
 *
 * Sprint 2.6 G3: each card now also surfaces the stage label inline
 * (in addition to the section heading) so that fast scrolling +
 * subsequent linking back to the card has clear context. Priority
 * chip uses the centralized `lib/ui/priority` palette to match the
 * rest of the codebase.
 */
export function PipelineList({ stages, leads }: Props) {
  // Sprint 3.5 G5 — mobile stage filter. `null` means «Все» (show every
  // stage section, prior behaviour). Selecting a stage collapses the
  // list to that section only — the audit caught that the kanban-to-list
  // collapse on mobile hid all per-stage navigation.
  const [filterStageId, setFilterStageId] = useState<string | null>(null);

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

  const visibleStages = filterStageId
    ? stages.filter((s) => s.id === filterStageId)
    : stages;

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Stage filter chips — horizontal scroll, sticky under the page
          header so it stays reachable while the list scrolls. */}
      <div className="sticky top-0 z-10 bg-brand-bg/95 backdrop-blur-sm px-4 py-2 border-b border-brand-border">
        <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <button
            type="button"
            onClick={() => setFilterStageId(null)}
            className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full type-caption font-semibold transition-colors ${
              filterStageId === null
                ? "bg-brand-accent text-white"
                : "bg-white border border-brand-border text-brand-muted hover:border-brand-accent/40"
            }`}
          >
            Все
            <span className={`${T.mono} tabular-nums opacity-80`}>
              {leads.length}
            </span>
          </button>
          {stages.map((s) => {
            const count = (grouped[s.id] ?? []).length;
            const selected = filterStageId === s.id;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setFilterStageId(s.id)}
                className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full type-caption font-semibold transition-colors ${
                  selected
                    ? "bg-brand-accent text-white"
                    : "bg-white border border-brand-border text-brand-muted hover:border-brand-accent/40"
                }`}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: s.color }}
                />
                <span className="truncate max-w-[140px]">{s.name}</span>
                <span className={`${T.mono} tabular-nums opacity-80`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="px-4 py-3">
      {visibleStages.map((stage) => {
        const stageLeads = grouped[stage.id] ?? [];
        if (stageLeads.length === 0 && filterStageId === null) return null;
        return (
          <section key={stage.id} className="mb-5">
            <div className="flex items-center gap-2 mb-2">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: stage.color }}
              />
              <h3 className="type-caption font-bold text-brand-primary truncate">
                {stage.name}
              </h3>
              <span className={`${T.mono} text-brand-muted tabular-nums`}>
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
                    className="flex items-center gap-3 px-3 py-2.5 bg-white border border-brand-border rounded-xl active:bg-brand-bg hover:border-brand-accent/30 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-brand-primary truncate">
                        {lead.company_name}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {/* Stage badge — visible on the card itself
                            so fast-scroll context isn't lost when
                            section headings scroll out of view. */}
                        <span
                          className={`inline-flex items-center gap-1 ${T.mono} uppercase text-brand-muted truncate`}
                          style={{ maxWidth: "60%" }}
                        >
                          <span
                            className="w-1.5 h-1.5 rounded-full shrink-0"
                            style={{ backgroundColor: stage.color }}
                          />
                          {stage.name}
                        </span>
                        {segCity && (
                          <span className={`${T.mono} text-brand-muted truncate lowercase`}>
                            · {segCity}
                          </span>
                        )}
                      </div>
                    </div>
                    {lead.priority && (
                      <span
                        className={`shrink-0 ${T.mono} font-bold px-1.5 py-0.5 rounded-md ${priorityChip(lead.priority)}`}
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

      {/* Empty state — either the whole pipeline is empty, or the
          user filtered to a stage with no leads. */}
      {filterStageId === null && leads.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-sm text-brand-muted">Ни одной карточки в воронке</p>
        </div>
      )}
      {filterStageId !== null &&
        (grouped[filterStageId] ?? []).length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-brand-muted">
              На этом этапе пока пусто
            </p>
            <button
              type="button"
              onClick={() => setFilterStageId(null)}
              className="mt-2 type-caption font-semibold text-brand-accent-text"
            >
              Показать все этапы
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
