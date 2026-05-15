"use client";
// PipelineEditor — Sprint 2.3 G3.
//
// Modal for create-and-edit of a workspace pipeline. Stages live in a
// dnd-kit sortable list; reordering rewrites `position` on save.
// Stage replacement on update is full (PATCH /api/pipelines/{id} sends
// the entire stages list back) — matches the backend's
// `repositories.replace_stages` contract.
//
// Field-name note: the row's «Цель (дней)» binds to `rot_days` (the
// rotting threshold from Sprint 1.2) — adding a separate
// `target_dwell_days` column would have been a 2.4+ schema change and
// the existing semantics already match what the editor surfaces.
import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  GripVertical,
  Loader2,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { ApiError } from "@/lib/api-client";
import {
  useCreatePipeline,
  useUpdatePipeline,
} from "@/lib/hooks/use-pipelines";
import type { Pipeline, PipelineCreateIn, StageIn } from "@/lib/types";

interface StageRow {
  // React key — survives reorder + add/delete without a stable backend id
  _clientId: string;
  // Existing stage IDs are not sent on save; the backend re-issues UUIDs
  // on full-replace. Kept here for readability + future merge-mode.
  id?: string;
  name: string;
  color: string;
  rot_days: number;
  is_won: boolean;
  is_lost: boolean;
}

const DEFAULT_COLOR = "#a1a1a6";

function newClientId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function emptyStage(position: number): StageRow {
  return {
    _clientId: newClientId(),
    name: position === 0 ? "Новый контакт" : "",
    color: DEFAULT_COLOR,
    rot_days: 7,
    is_won: false,
    is_lost: false,
  };
}

function stagesFromPipeline(p: Pipeline): StageRow[] {
  return [...p.stages]
    .sort((a, b) => a.position - b.position)
    .map((s) => ({
      _clientId: newClientId(),
      id: s.id,
      name: s.name,
      color: s.color,
      rot_days: s.rot_days,
      is_won: s.is_won,
      is_lost: s.is_lost,
    }));
}

function buildStagesIn(rows: StageRow[]): StageIn[] {
  return rows.map((r, i) => ({
    name: r.name.trim(),
    position: i,
    color: r.color || DEFAULT_COLOR,
    rot_days: Number.isFinite(r.rot_days) ? r.rot_days : 7,
    is_won: r.is_won,
    is_lost: r.is_lost,
  }));
}

interface Props {
  open: boolean;
  pipeline?: Pipeline; // undefined = create mode
  onClose: () => void;
  onSaved: (saved: Pipeline) => void;
}

export function PipelineEditor({ open, pipeline, onClose, onSaved }: Props) {
  const isEdit = !!pipeline;

  const [name, setName] = useState("");
  const [stages, setStages] = useState<StageRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const create = useCreatePipeline();
  const update = useUpdatePipeline();
  const busy = create.isPending || update.isPending;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  // Reset state every time the editor opens.
  useEffect(() => {
    if (!open) return;
    setError(null);
    if (pipeline) {
      setName(pipeline.name);
      setStages(stagesFromPipeline(pipeline));
    } else {
      setName("");
      setStages([emptyStage(0), emptyStage(1), emptyStage(2)]);
    }
  }, [open, pipeline]);

  // Esc closes — but not while a save is in flight.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onClose]);

  const stageIds = useMemo(() => stages.map((s) => s._clientId), [stages]);

  if (!open) return null;

  function addStage() {
    setStages((prev) => [...prev, emptyStage(prev.length)]);
  }

  function removeStage(clientId: string) {
    setStages((prev) => prev.filter((s) => s._clientId !== clientId));
  }

  function patchStage(clientId: string, patch: Partial<StageRow>) {
    setStages((prev) =>
      prev.map((s) => (s._clientId === clientId ? { ...s, ...patch } : s)),
    );
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    setStages((prev) => {
      const oldIndex = prev.findIndex((s) => s._clientId === active.id);
      const newIndex = prev.findIndex((s) => s._clientId === over.id);
      if (oldIndex < 0 || newIndex < 0) return prev;
      return arrayMove(prev, oldIndex, newIndex);
    });
  }

  function handleSave() {
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Название обязательно");
      return;
    }
    const cleaned = stages
      .map((s) => ({ ...s, name: s.name.trim() }))
      .filter((s) => s.name);
    if (cleaned.length === 0) {
      setError("Нужна хотя бы одна стадия");
      return;
    }

    const onSuccess = (saved: Pipeline) => onSaved(saved);
    const onError = (err: ApiError) => {
      const detail =
        err.body && typeof err.body === "object"
          ? (err.body as { detail?: unknown }).detail
          : null;
      setError(
        typeof detail === "string"
          ? detail
          : "Не удалось сохранить воронку",
      );
    };

    if (isEdit && pipeline) {
      update.mutate(
        {
          id: pipeline.id,
          body: { name: trimmed, stages: buildStagesIn(cleaned) },
        },
        { onSuccess, onError },
      );
    } else {
      const body: PipelineCreateIn = {
        name: trimmed,
        stages: buildStagesIn(cleaned),
      };
      create.mutate(body, { onSuccess, onError });
    }
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={busy ? undefined : onClose}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label={isEdit ? "Редактирование воронки" : "Новая воронка"}
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-black/5 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
                Воронка
              </div>
              <h2 className="text-lg font-bold tracking-tight text-ink mt-0.5 truncate">
                {isEdit ? pipeline?.name : "Новая воронка"}
              </h2>
            </div>
            <button
              onClick={busy ? undefined : onClose}
              disabled={busy}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-muted-2 hover:bg-canvas hover:text-ink transition-colors disabled:opacity-40"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="px-6 py-5 overflow-y-auto flex-1 space-y-5">
            {/* Name */}
            <div>
              <label className="block text-[11px] font-mono uppercase tracking-wide text-muted-3 mb-1.5">
                Название
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Например: Партнёры"
                className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-colors"
              />
            </div>

            {/* Stages */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-[11px] font-mono uppercase tracking-wide text-muted-3">
                  Стадии
                </label>
                <span className="text-[10px] font-mono text-muted-3">
                  {stages.length} {stages.length === 1 ? "стадия" : "стадий"}
                </span>
              </div>

              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={onDragEnd}
              >
                <SortableContext
                  items={stageIds}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="flex flex-col gap-1.5">
                    {stages.map((s) => (
                      <StageRowItem
                        key={s._clientId}
                        row={s}
                        onPatch={(patch) => patchStage(s._clientId, patch)}
                        onRemove={() => removeStage(s._clientId)}
                        canRemove={stages.length > 1}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>

              <button
                type="button"
                onClick={addStage}
                className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-[12px] font-semibold text-muted hover:text-ink bg-canvas hover:bg-canvas-2 transition-colors"
              >
                <Plus size={13} />
                Добавить стадию
              </button>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-black/5 flex items-center justify-between">
            {error ? (
              <div className="flex items-center gap-1.5 text-[12px] text-rose">
                <AlertCircle size={13} />
                <span>{error}</span>
              </div>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-2">
              <button
                onClick={busy ? undefined : onClose}
                disabled={busy}
                className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={handleSave}
                disabled={busy}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 transition-all duration-300"
              >
                {busy && <Loader2 size={14} className="animate-spin" />}
                {busy ? "Сохраняем…" : "Сохранить"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sortable row
// ---------------------------------------------------------------------------

function StageRowItem({
  row,
  onPatch,
  onRemove,
  canRemove,
}: {
  row: StageRow;
  onPatch: (patch: Partial<StageRow>) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: row._clientId });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="grid grid-cols-[20px_1fr_64px_84px_28px] items-center gap-2 bg-canvas/60 border border-black/5 rounded-xl px-2 py-1.5"
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="text-muted-3 hover:text-ink cursor-grab active:cursor-grabbing touch-none"
        aria-label="Перетащить"
      >
        <GripVertical size={14} />
      </button>

      <input
        type="text"
        value={row.name}
        onChange={(e) => onPatch({ name: e.target.value })}
        placeholder="Название стадии"
        className="px-2 py-1 text-sm bg-white border border-black/10 rounded-lg outline-none focus:border-brand-accent/40 transition-colors min-w-0"
      />

      <input
        type="color"
        value={row.color}
        onChange={(e) => onPatch({ color: e.target.value })}
        title="Цвет стадии"
        className="w-full h-7 border border-black/10 rounded-lg cursor-pointer"
      />

      <div className="flex items-center gap-1">
        <input
          type="number"
          min={0}
          max={365}
          value={row.rot_days}
          onChange={(e) =>
            onPatch({
              rot_days: Math.max(
                0,
                Math.min(365, Number(e.target.value) || 0),
              ),
            })
          }
          className="w-14 px-1.5 py-1 text-sm font-mono bg-white border border-black/10 rounded-lg outline-none focus:border-brand-accent/40 transition-colors text-right tabular-nums"
          title="Срок до пометки «протухает»"
        />
        <span className="text-[10px] font-mono text-muted-3">дн.</span>
      </div>

      <button
        type="button"
        onClick={onRemove}
        disabled={!canRemove}
        className="text-muted-3 hover:text-rose disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        aria-label="Удалить стадию"
        title={canRemove ? "Удалить" : "Нужна хотя бы одна стадия"}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
