"use client";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { Stage, LeadOut } from "@/lib/types";
import { PipelineLeadCard } from "./PipelineLeadCard";

interface Props {
  stage: Stage;
  leads: LeadOut[];
  allVisibleLeads: LeadOut[];
}

export function PipelineColumn({ stage, leads, allVisibleLeads }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });

  return (
    <div className="flex flex-col shrink-0 w-[230px]">
      {/* Column header */}
      <div className="mb-2">
        {/* Color stripe */}
        <div
          className="h-1 rounded-full mb-2"
          style={{ backgroundColor: stage.color }}
        />
        <div className="flex items-center justify-between gap-1">
          <p className="font-semibold text-sm text-ink leading-snug truncate">
            {stage.name}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            {stage.rot_days > 0 && (
              <span className="text-[9px] font-mono text-muted-3 bg-black/5 px-1.5 py-0.5 rounded-full">
                {stage.rot_days}д
              </span>
            )}
            <span className="text-[10px] font-mono text-muted-2 bg-black/5 px-1.5 py-0.5 rounded-full">
              {leads.length}
            </span>
          </div>
        </div>
      </div>

      {/* Cards area */}
      <div
        ref={setNodeRef}
        className={`flex flex-col gap-2 flex-1 min-h-[80px] rounded-xl p-2 transition-colors duration-200 ${
          isOver ? "bg-accent/5 ring-1 ring-accent/20" : "bg-transparent"
        }`}
      >
        <SortableContext
          items={leads.map((l) => l.id)}
          strategy={verticalListSortingStrategy}
        >
          {leads.map((lead) => (
            <PipelineLeadCard
              key={lead.id}
              lead={lead}
              visibleLeads={allVisibleLeads}
            />
          ))}
        </SortableContext>

        {leads.length === 0 && (
          <div className="flex-1 flex items-center justify-center border border-dashed border-black/10 rounded-lg min-h-[60px]">
            <p className="text-[10px] text-muted-3 text-center px-2">
              Перетащите карточку сюда
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
