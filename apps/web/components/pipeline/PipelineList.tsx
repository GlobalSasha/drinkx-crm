"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Phone } from "lucide-react";
import type { LeadListItem, Stage } from "@/lib/types";
import { priorityChip } from "@/lib/ui/priority";
import { C, T } from "@/lib/design-system";
import { listCallPhone, sortByUrgency, taskLabel, taskUrgency, type TaskUrgency } from "@/lib/my-leads";

interface Props {
  stages: Stage[];
  leads: LeadListItem[];
}

type ViewMode = "urgent" | "stages";
const VIEW_KEY = "drinkx:my-leads-view";

const URGENCY_TEXT: Record<TaskUrgency, string> = {
  overdue: "text-rose",
  today: "text-brand-accent-text",
  upcoming: "text-brand-muted",
  nodue: "text-brand-muted",
  none: "text-warning",
};

/**
 * Mobile body of /pipeline («Мои лиды» on a phone). Two views:
 * - «Срочные» (default): one flat list, what's burning first — overdue
 *   tasks, today's, upcoming, tasks without a date, then leads with no
 *   task at all.
 * - «По этапам»: the earlier list grouped by stage.
 * Stage chips filter both. Each row: open the card, or call straight away.
 * PipelineHeader still renders above (search + «+ Лид»).
 */
export function PipelineList({ stages, leads }: Props) {
  // `null` means «Все». Selecting a stage narrows either view to it.
  const [filterStageId, setFilterStageId] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("urgent");
  // One clock per data refresh, so labels and order agree within a render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const now = useMemo(() => new Date(), [leads]);

  // Remembered per browser — a convenience, so storage errors are ignored.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_KEY);
      if (saved === "urgent" || saved === "stages") setView(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);
  function changeView(next: ViewMode) {
    setView(next);
    try {
      window.localStorage.setItem(VIEW_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }

  const stageById = useMemo(() => new Map(stages.map((s) => [s.id, s])), [stages]);

  const grouped = useMemo(() => {
    const m: Record<string, LeadListItem[]> = {};
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

  const urgentLeads = useMemo(() => {
    const pool = filterStageId ? grouped[filterStageId] ?? [] : leads;
    return sortByUrgency(pool, now);
  }, [filterStageId, grouped, leads, now]);

  const stageFor = (lead: LeadListItem) =>
    (lead.stage_id ? stageById.get(lead.stage_id) : undefined) ?? stages[0];

  return (
    <div className="flex-1 overflow-y-auto">
      {/* View switch + stage chips — sticky under the page header so
          they stay reachable while the list scrolls. */}
      <div className="sticky top-0 z-10 bg-brand-bg/95 backdrop-blur-sm px-4 py-2 border-b border-brand-border flex flex-col gap-2">
        <div
          role="tablist"
          aria-label="Вид списка"
          className="flex gap-1 bg-white border border-brand-border rounded-full p-0.5 self-start"
        >
          {(
            [
              ["urgent", "Срочные"],
              ["stages", "По этапам"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={view === key}
              onClick={() => changeView(key)}
              className={`px-3 py-1 rounded-full type-button transition-colors ${
                view === key ? "bg-brand-accent text-white" : "text-brand-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5 overflow-x-auto -mx-1 px-1 pb-0.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <button
            type="button"
            onClick={() => setFilterStageId(null)}
            className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full type-button transition-colors ${
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
                className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full type-button transition-colors ${
                  selected
                    ? "bg-brand-accent text-white"
                    : "bg-white border border-brand-border text-brand-muted hover:border-brand-accent/40"
                }`}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: s.color }}
                />
                <span className="truncate max-w-36">{s.name}</span>
                <span className={`${T.mono} tabular-nums opacity-80`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* pb-24: room for the phone tab bar fixed at the bottom. */}
      <div className="px-4 pt-3 pb-24">
        {view === "urgent" ? (
          <div className="flex flex-col gap-1.5">
            {urgentLeads.map((lead) => (
              <LeadRow key={lead.id} lead={lead} stage={stageFor(lead)} now={now} />
            ))}
          </div>
        ) : (
          visibleStages.map((stage) => {
            const stageLeads = grouped[stage.id] ?? [];
            if (stageLeads.length === 0 && filterStageId === null) return null;
            return (
              <section key={stage.id} className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: stage.color }}
                  />
                  <h3 className="type-caption font-semibold text-brand-primary truncate">
                    {stage.name}
                  </h3>
                  <span className={`${T.mono} text-brand-muted tabular-nums`}>
                    {stageLeads.length}
                  </span>
                </div>
                <div className="flex flex-col gap-1.5">
                  {stageLeads.map((lead) => (
                    <LeadRow key={lead.id} lead={lead} stage={stage} now={now} />
                  ))}
                </div>
              </section>
            );
          })
        )}

        {/* Empty states — the whole list is empty, or the chosen stage is. */}
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
                className="mt-2 type-button text-brand-accent-text"
              >
                Показать все этапы
              </button>
            </div>
          )}
      </div>
    </div>
  );
}

function LeadRow({
  lead,
  stage,
  now,
}: {
  lead: LeadListItem;
  stage: Stage | undefined;
  now: Date;
}) {
  const phone = listCallPhone(lead);
  const urgency = taskUrgency(lead, now);
  const segCity = [lead.segment, lead.city].filter(Boolean).join(", ");
  return (
    <div className="flex items-stretch bg-white border border-brand-border rounded-lg overflow-hidden">
      <Link
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        href={`/leads/${lead.id}` as any}
        className={`flex-1 min-w-0 flex items-center gap-3 px-3 py-2.5 active:bg-brand-bg transition-colors ${C.focusRing}`}
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-brand-primary truncate">
            {lead.company_name}
          </p>
          <p className={`type-label mt-0.5 truncate ${URGENCY_TEXT[urgency]}`}>
            {taskLabel(lead, now)}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {stage && (
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
            )}
            {segCity && (
              <span className={`${T.mono} text-brand-muted truncate lowercase`}>
                · {segCity}
              </span>
            )}
          </div>
        </div>
        {lead.priority && (
          <span
            className={`shrink-0 ${T.mono} font-semibold px-1.5 py-0.5 rounded-md ${priorityChip(lead.priority)}`}
          >
            {lead.priority}
          </span>
        )}
      </Link>
      {phone && (
        <a
          href={`tel:${phone}`}
          aria-label={`Позвонить: ${lead.company_name}`}
          className={`shrink-0 w-12 flex items-center justify-center border-l border-brand-border text-brand-accent-text active:bg-brand-soft transition-colors ${C.focusRing}`}
        >
          <Phone size={18} aria-hidden />
        </a>
      )}
    </div>
  );
}
