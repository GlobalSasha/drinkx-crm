"use client";
import { useRouter } from "next/navigation";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AlertTriangle, Clock } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { priorityChip } from "@/lib/ui/priority";
import { C } from "@/lib/design-system";

interface Props {
  lead: LeadOut;
}

export function PipelineLeadCard({ lead }: Props) {
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

  const isRotting = lead.is_rotting_stage || lead.is_rotting_next_step;

  // Priority A pops with the solid brand accent — everything else
  // keeps the existing tier palette (B/C/D) but in pill form.
  const priorityClass =
    lead.priority === "A"
      ? "bg-brand-accent text-white"
      : priorityChip(lead.priority);

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => router.push(`/leads/${lead.id}`)}
      className="font-sans bg-white border border-brand-border rounded-2xl p-3 cursor-pointer select-none transition-opacity duration-200"
    >
      {/* Company name */}
      <div className="flex items-start justify-between gap-1 mb-1.5">
        <p className={`${C.bodySm} font-bold ${C.color.text} truncate leading-snug`}>
          {lead.company_name}
        </p>
        {isRotting && (
          <AlertTriangle size={13} className="text-warning shrink-0 mt-0.5" />
        )}
      </div>

      {/* Segment + city */}
      {(lead.segment || lead.city) && (
        <p className={`font-mono text-[10px] uppercase tracking-[0.08em] ${C.color.mutedLight} truncate mb-2`}>
          {[lead.segment, lead.city].filter(Boolean).join(" · ")}
        </p>
      )}

      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-1">
        {lead.priority && (
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${priorityClass}`}
          >
            {lead.priority}
          </span>
        )}

        {lead.score > 0 && (
          <span className="text-[10px] font-bold font-mono bg-brand-soft text-brand-accent-text px-2 py-0.5 rounded-full tabular-nums">
            {lead.score}
          </span>
        )}

        {lead.fit_score != null && (
          <span className="text-[10px] font-mono bg-brand-panel text-brand-muted-strong px-2 py-0.5 rounded-full tabular-nums">
            fit {lead.fit_score}
          </span>
        )}

        {isRotting && (
          <span className="text-[10px] font-mono flex items-center gap-0.5 text-warning">
            <Clock size={10} />
            rot
          </span>
        )}
      </div>
    </div>
  );
}
