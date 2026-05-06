"use client";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AlertTriangle, Clock } from "lucide-react";
import type { LeadOut } from "@/lib/types";
import { usePipelineStore } from "@/lib/store/pipeline-store";

const PRIORITY_STYLES: Record<string, string> = {
  A: "bg-accent/10 text-accent",
  B: "bg-success/10 text-success",
  C: "bg-warning/10 text-warning",
  D: "bg-black/5 text-muted",
};

interface Props {
  lead: LeadOut;
  visibleLeads: LeadOut[];
}

export function PipelineLeadCard({ lead, visibleLeads }: Props) {
  const { openDrawer } = usePipelineStore();

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

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => openDrawer(lead, visibleLeads)}
      className="bg-white border border-black/5 rounded-xl p-3 shadow-soft cursor-pointer select-none hover:shadow-md hover:-translate-y-0.5 transition-all duration-300 ease-soft group"
    >
      {/* Company name */}
      <div className="flex items-start justify-between gap-1 mb-1.5">
        <p className="font-semibold text-sm text-ink truncate leading-snug">
          {lead.company_name}
        </p>
        {isRotting && (
          <AlertTriangle size={13} className="text-warning shrink-0 mt-0.5" />
        )}
      </div>

      {/* Segment + city */}
      {(lead.segment || lead.city) && (
        <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-2 truncate mb-2">
          {[lead.segment, lead.city].filter(Boolean).join(" · ")}
        </p>
      )}

      {/* Badges row */}
      <div className="flex flex-wrap items-center gap-1">
        {lead.priority && (
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
              PRIORITY_STYLES[lead.priority] ?? "bg-black/5 text-muted"
            }`}
          >
            {lead.priority}
          </span>
        )}

        {lead.score > 0 && (
          <span className="text-[10px] font-mono bg-black/5 text-muted px-1.5 py-0.5 rounded-md">
            {lead.score}
          </span>
        )}

        {lead.fit_score != null && (
          <span className="text-[10px] font-mono bg-accent/10 text-accent px-1.5 py-0.5 rounded-md">
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
