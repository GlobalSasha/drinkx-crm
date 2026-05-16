"use client";
import { memo } from "react";
import { useRouter } from "next/navigation";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Bell, ClipboardList, Star } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

/**
 * Pipeline Kanban card — Sprint «Lead Card Redesign».
 *
 * Fixed three-row layout (~88px tall):
 *   1. Company name
 *   2. ★ Primary contact name — empty (whitespace) when no primary set
 *      so the card height stays constant across the column
 *   3. Bottom info bar — segment chip, open tasks / followups
 *      counters (only when > 0), and a date on the right
 *
 * Removed from the previous design (intentionally): priority badge,
 * score, fit_score, rotting indicators. The pipeline view is now a
 * pure «who / what / when» surface; AI and rotting metadata live in
 * the Lead Card detail view.
 */
function PipelineLeadCardImpl({ lead }: Props) {
  const router = useRouter();

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: lead.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      router.push(`/leads/${lead.id}`);
    }
  }

  // Date right-aligned in the bottom row: assigned_at if known, else
  // created_at. Format DD.MM.YY. Both fields are guaranteed populated
  // for any lead the list query returns, so the fallback chain is
  // mostly defensive against future schema changes.
  const dateIso = lead.assigned_at ?? lead.created_at;
  const dateLabel = dateIso ? formatDDMMYY(dateIso) : "";

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      role="link"
      tabIndex={0}
      aria-label={`Открыть лид ${lead.company_name}`}
      onClick={() => router.push(`/leads/${lead.id}`)}
      onKeyDown={handleKey}
      className="font-sans bg-white border border-brand-border rounded-md p-3 h-[88px] flex flex-col justify-between cursor-pointer select-none transition-opacity duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-brand-bg"
    >
      {/* Row 1 — company name (bold, single line) */}
      <p className={`type-caption font-bold ${C.color.text} truncate leading-snug`}>
        {lead.company_name}
      </p>

      {/* Row 2 — primary contact name with star prefix. Always
          rendered (with placeholder) so the card height stays
          constant in the column. */}
      <p className="flex items-center gap-1 type-caption text-brand-muted-strong truncate min-h-[16px]">
        {lead.primary_contact_name ? (
          <>
            <Star size={11} fill="currentColor" className="text-brand-accent shrink-0" />
            <span className="truncate">{lead.primary_contact_name}</span>
          </>
        ) : (
          <span className="opacity-0">—</span>
        )}
      </p>

      {/* Row 3 — bottom info bar */}
      <div className="flex items-center gap-1.5 text-[10px] text-brand-muted">
        {lead.segment && (
          <span className="font-mono uppercase tracking-[0.06em] bg-brand-panel text-brand-muted-strong px-1.5 py-0.5 rounded-md truncate max-w-[90px]">
            {lead.segment}
          </span>
        )}
        {lead.open_tasks_count > 0 && (
          <span
            className="inline-flex items-center gap-0.5 tabular-nums"
            title={`Открытых задач: ${lead.open_tasks_count}`}
          >
            <ClipboardList size={10} />
            {lead.open_tasks_count}
          </span>
        )}
        {lead.open_followups_count > 0 && (
          <span
            className="inline-flex items-center gap-0.5 tabular-nums"
            title={`Открытых follow-up: ${lead.open_followups_count}`}
          >
            <Bell size={10} />
            {lead.open_followups_count}
          </span>
        )}
        <span className="ml-auto font-mono tabular-nums shrink-0">
          {dateLabel}
        </span>
      </div>
    </div>
  );
}

function formatDDMMYY(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yy = String(d.getFullYear() % 100).padStart(2, "0");
  return `${dd}.${mm}.${yy}`;
}

export const PipelineLeadCard = memo(PipelineLeadCardImpl);
