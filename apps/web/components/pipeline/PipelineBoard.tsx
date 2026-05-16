"use client";
import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
} from "@dnd-kit/core";
import { useState, useCallback } from "react";
import type { Stage, LeadOut } from "@/lib/types";
import { useMoveStage } from "@/lib/hooks/use-leads";
import { ApiError } from "@/lib/api-client";
import { PipelineColumn } from "./PipelineColumn";
import { PipelineLeadCard } from "./PipelineLeadCard";
import { Toast } from "@/components/ui/Toast";

interface Props {
  stages: Stage[];
  leads: LeadOut[];
}

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function PipelineBoard({ stages, leads }: Props) {
  const moveStage = useMoveStage();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastState[]>([]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const addToast = useCallback(
    (message: string, type: "error" | "success" = "error") => {
      const id = Date.now();
      setToasts((prev) => [...prev, { id, message, type }]);
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
    },
    []
  );

  const leadsPerStage = buildLeadsPerStage(stages, leads);
  const activeLead = activeId ? leads.find((l) => l.id === activeId) : null;

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;

    const leadId = active.id as string;
    const lead = leads.find((l) => l.id === leadId);
    if (!lead) return;

    // `over.id` may be a stage id (droppable) or another card id (sortable).
    let targetStageId: string = over.id as string;
    const overLead = leads.find((l) => l.id === targetStageId);
    if (overLead) {
      targetStageId = overLead.stage_id ?? targetStageId;
    }

    if (!targetStageId || targetStageId === lead.stage_id) return;

    if (!UUID_RE.test(targetStageId)) {
      // No real stage UUIDs yet (empty board); show a hint.
      addToast("Создайте первый лид, затем перетаскивание станет доступно", "error");
      return;
    }

    moveStage.mutate(
      { leadId, body: { stage_id: targetStageId }, previousLead: lead },
      {
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            const detail = err.body as {
              message?: string;
              violations?: { message: string }[];
            };
            const msgs =
              detail.violations?.map((v) => v.message).join("; ") ??
              detail.message ??
              "Переход заблокирован";
            addToast(`Заблокировано: ${msgs}`, "error");
          } else {
            addToast("Ошибка при перемещении карточки", "error");
          }
        },
      }
    );
  }

  return (
    <div className="relative flex-1 min-h-0">
      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex overflow-x-auto h-full px-6 py-4 pb-6">
          {stages.map((stage) => (
            <PipelineColumn
              key={stage.id}
              stage={stage}
              leads={leadsPerStage[stage.id] ?? []}
            />
          ))}
        </div>

        <DragOverlay>
          {activeLead ? <PipelineLeadCard lead={activeLead} /> : null}
        </DragOverlay>
      </DndContext>

      {/* Toast container */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-50 pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} type={t.type} />
        ))}
      </div>
    </div>
  );
}

function buildLeadsPerStage(
  stages: Stage[],
  leads: LeadOut[]
): Record<string, LeadOut[]> {
  const map: Record<string, LeadOut[]> = {};
  stages.forEach((s) => (map[s.id] = []));

  leads.forEach((lead) => {
    const sid = lead.stage_id;
    if (sid && map[sid] !== undefined) {
      map[sid].push(lead);
    } else {
      // Unknown stage_id — put in first column so the card is visible.
      const first = stages[0];
      if (first) map[first.id].push(lead);
    }
  });

  return map;
}
