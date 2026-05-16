"use client";
import { memo } from "react";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { Stage, LeadOut } from "@/lib/types";
import { PipelineLeadCard } from "./PipelineLeadCard";
import { C } from "@/lib/design-system";

interface Props {
  stage: Stage;
  leads: LeadOut[];
}

function PipelineColumnImpl({ stage, leads }: Props) {
  const { setNodeRef, isOver } = useDroppable({ id: stage.id });

  // Column geometry:
  //   - No outer card chrome (was bg-brand-bg + rounded-[2rem] + border).
  //     The previous rounded card couldn't grow vertically beyond the
  //     viewport, so a tall column overflowed its own border. Now the
  //     column is a transparent flex container, cards live directly on
  //     the page background.
  //   - Vertical 1px divider between stages — `border-l` on every
  //     column except the first via `first:border-l-0`. Cleaner reading
  //     than 11 stacked rounded rectangles.
  //   - `min-h-0` + `overflow-y-auto` on the cards area so a tall
  //     stack scrolls inside the column instead of pushing the page.
  return (
    <div
      id={`stage-col-${stage.id}`}
      className="font-sans flex flex-col shrink-0 w-[260px] min-h-0 pl-4 first:pl-0 pr-2 border-l border-brand-border first:border-l-0"
    >
      {/* Column header */}
      <div className="pb-3">
        {/* Color stripe — keeps stage's individual hue as a thin signal */}
        <div
          className="h-1 rounded-full mb-3"
          style={{ backgroundColor: stage.color }}
        />
        <div className="flex items-center justify-between gap-2">
          <p className={`type-caption ${C.color.text} truncate`}>
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

      {/* Cards area — scrolls vertically when the stack outgrows the
          column height. `min-h-0` is the flex-child trick that allows
          the child to shrink below its content size so the overflow
          actually kicks in. */}
      <div
        ref={setNodeRef}
        className={`flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto rounded-2xl p-1 transition-colors duration-200 ${
          isOver ? "bg-brand-soft ring-1 ring-brand-accent/20" : "bg-transparent"
        }`}
      >
        <SortableContext
          items={leads.map((l) => l.id)}
          strategy={verticalListSortingStrategy}
        >
          {leads.map((lead) => (
            <PipelineLeadCard key={lead.id} lead={lead} />
          ))}
        </SortableContext>

        {leads.length === 0 && isOver && (
          <div className="flex-1 flex items-center justify-center border border-dashed border-brand-border rounded-2xl min-h-[60px]">
            <p className={`type-caption ${C.color.mutedLight} text-center px-2`}>
              Перетащите карточку сюда
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export const PipelineColumn = memo(PipelineColumnImpl);
