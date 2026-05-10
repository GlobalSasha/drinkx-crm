"use client";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { Stage, LeadOut } from "@/lib/types";
import { PipelineLeadCard } from "./PipelineLeadCard";
import { C } from "@/lib/design-system";

interface Props {
  stage: Stage;
  leads: LeadOut[];
  allVisibleLeads: LeadOut[];
}

export function PipelineColumn({ stage, leads, allVisibleLeads }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });

  return (
    <div
      id={`stage-col-${stage.id}`}
      className="font-sans flex flex-col shrink-0 w-[260px] bg-brand-bg border border-brand-border rounded-[2rem] p-3"
    >
      {/* Column header */}
      <div className="px-2 pb-3">
        {/* Color stripe — keeps stage's individual hue as a thin signal */}
        <div
          className="h-1 rounded-full mb-3"
          style={{ backgroundColor: stage.color }}
        />
        <div className="flex items-center justify-between gap-2">
          <p className={`${C.caption} ${C.color.text} truncate`}>
            {stage.name}
          </p>
          <div className="flex items-center gap-1 shrink-0">
            {stage.rot_days > 0 && (
              <span className="text-[9px] font-mono text-brand-muted bg-brand-panel px-1.5 py-0.5 rounded-full">
                {stage.rot_days}д
              </span>
            )}
            <span className="text-[10px] font-mono text-brand-muted-strong bg-brand-panel px-1.5 py-0.5 rounded-full">
              {leads.length}
            </span>
          </div>
        </div>
      </div>

      {/* Cards area */}
      <div
        ref={setNodeRef}
        className={`flex flex-col gap-2 flex-1 min-h-[80px] rounded-2xl p-1 transition-colors duration-200 ${
          isOver ? "bg-brand-soft ring-1 ring-brand-accent/20" : "bg-transparent"
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

        {leads.length === 0 && isOver && (
          <div className="flex-1 flex items-center justify-center border border-dashed border-brand-border rounded-2xl min-h-[60px]">
            <p className={`${C.bodyXs} ${C.color.mutedLight} text-center px-2`}>
              Перетащите карточку сюда
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
