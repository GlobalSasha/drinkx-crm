"use client";
// PipelinesSection — Sprint 2.3 G3.
//
// Renders the workspace's pipelines as a table with set-default + delete
// actions. Read access is open to all roles; mutating actions are gated
// to admin/head via useMe(). Friendly delete-conflict modals consume the
// backend's structured 409 detail (`pipeline_has_leads` /
// `pipeline_is_default`) so the UX matches what's blocking the delete
// without a second round-trip.
import { useState } from "react";
import { Loader2, Plus, Star, Trash2 } from "lucide-react";

import { T } from "@/lib/design-system";
import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import {
  useDeletePipeline,
  usePipelines,
  useSetDefaultPipeline,
} from "@/lib/hooks/use-pipelines";
import type { Pipeline, PipelineDeleteConflict } from "@/lib/types";

import { PipelineEditor } from "./PipelineEditor";

interface DeleteState {
  pipeline: Pipeline;
  // null while we haven't asked the backend yet.
  // 'confirm' means the backend let us through and we want a final OK.
  // A conflict object means the backend said no — render the friendly
  // modal explaining why.
  state: "confirm" | PipelineDeleteConflict;
}

export function PipelinesSection() {
  const meQuery = useMe();
  const pipelinesQuery = usePipelines();
  const setDefault = useSetDefaultPipeline();
  const del = useDeletePipeline();

  const isAdminOrHead =
    meQuery.data?.role === "admin" || meQuery.data?.role === "head";
  const defaultPipelineId =
    meQuery.data?.workspace.default_pipeline_id ?? null;
  const pipelines = pipelinesQuery.data ?? [];

  const [editing, setEditing] = useState<Pipeline | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [deleteState, setDeleteState] = useState<DeleteState | null>(null);

  function openCreate() {
    setEditing(null);
    setEditorOpen(true);
  }

  function openEdit(p: Pipeline) {
    setEditing(p);
    setEditorOpen(true);
  }

  function onSetDefault(p: Pipeline) {
    setDefault.mutate(p.id);
  }

  /**
   * Try to delete. The backend either succeeds or surfaces a structured
   * 409 — we read `error.body.detail` for the conflict shape and pivot
   * the modal accordingly. No pre-flight check endpoint: the optimistic
   * DELETE is already the cheapest probe, and the structured detail
   * carries everything the UI needs.
   */
  function startDelete(p: Pipeline) {
    setDeleteState({ pipeline: p, state: "confirm" });
  }

  function confirmDelete(p: Pipeline) {
    del.mutate(p.id, {
      onSuccess: () => {
        setDeleteState(null);
      },
      onError: (err: ApiError) => {
        const detail =
          err.body && typeof err.body === "object"
            ? (err.body as { detail?: unknown }).detail
            : null;
        // The backend shape: { code: ..., lead_count?: ..., message: ... }
        if (
          detail &&
          typeof detail === "object" &&
          "code" in (detail as object)
        ) {
          setDeleteState({
            pipeline: p,
            state: detail as PipelineDeleteConflict,
          });
        } else {
          // Generic failure — fall back to a free-text error in the
          // existing modal so the manager isn't left guessing.
          setDeleteState({
            pipeline: p,
            state: {
              code: "pipeline_has_leads",
              lead_count: 0,
              message:
                typeof detail === "string"
                  ? detail
                  : "Не удалось удалить воронку",
            } as PipelineDeleteConflict,
          });
        }
      },
    });
  }

  if (pipelinesQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (pipelinesQuery.isError) {
    return (
      <p className="text-sm text-rose py-8 text-center">
        Не удалось загрузить воронки. Попробуйте позже.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="type-card-title">Воронки</h2>
          <p className="text-xs text-muted-2 mt-0.5">
            Создавайте отдельные воронки для разных типов сделок: продажи,
            партнёры, апсейл и т.д.
          </p>
        </div>
        {isAdminOrHead && (
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90 active:scale-[0.98] transition-all duration-300"
          >
            <Plus size={14} />
            Новая воронка
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-canvas/60">
            <tr className="border-b border-black/5">
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold`}>
                Название
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[110px]`}>
                Стадий
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[180px]`}>
                По умолчанию
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[80px] text-right`}>
                <span className="sr-only">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {pipelines.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center">
                  <p className="text-sm text-muted-2">Воронок пока нет</p>
                </td>
              </tr>
            )}
            {pipelines.map((p) => {
              const isDefault = p.id === defaultPipelineId;
              return (
                <tr
                  key={p.id}
                  className="border-b border-black/5 last:border-0 hover:bg-canvas/40 transition-colors"
                >
                  <td className="px-4 py-3 align-middle">
                    <button
                      onClick={() => openEdit(p)}
                      className="text-sm font-semibold text-ink hover:text-brand-accent transition-colors text-left"
                    >
                      {p.name}
                    </button>
                  </td>
                  <td className="px-4 py-3 align-middle">
                    <span className={`${T.mono} text-muted-2 tabular-nums`}>
                      {p.stages.length}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-middle">
                    {isDefault ? (
                      <span className={`inline-flex items-center gap-1 ${T.mono} uppercase bg-brand-soft text-brand-accent rounded-pill px-2 py-0.5`}>
                        <Star size={10} />
                        по умолчанию
                      </span>
                    ) : isAdminOrHead ? (
                      <button
                        onClick={() => onSetDefault(p)}
                        disabled={setDefault.isPending}
                        className="text-xs font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
                      >
                        Сделать основной
                      </button>
                    ) : (
                      <span className="text-xs text-muted-3">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 align-middle text-right">
                    {isAdminOrHead && (
                      <button
                        onClick={() => startDelete(p)}
                        className="p-1.5 text-muted-3 hover:text-rose hover:bg-rose/10 rounded-lg transition-colors"
                        aria-label="Удалить воронку"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Editor */}
      <PipelineEditor
        open={editorOpen}
        pipeline={editing ?? undefined}
        onClose={() => setEditorOpen(false)}
        onSaved={() => {
          setEditorOpen(false);
        }}
      />

      {/* Delete modals */}
      {deleteState && (
        <DeleteModal
          state={deleteState}
          busy={del.isPending}
          onCancel={() => setDeleteState(null)}
          onConfirm={() => confirmDelete(deleteState.pipeline)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Delete modal — three branches
// ---------------------------------------------------------------------------

function DeleteModal({
  state,
  busy,
  onCancel,
  onConfirm,
}: {
  state: DeleteState;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { pipeline } = state;
  const isConfirm = state.state === "confirm";
  const conflict = isConfirm ? null : (state.state as PipelineDeleteConflict);

  let title = `Удалить воронку «${pipeline.name}»?`;
  let body: React.ReactNode;
  let primaryLabel = "Удалить";
  let primaryAction = onConfirm;
  let primaryStyle =
    "bg-rose text-white hover:bg-rose/90 active:scale-[0.98]";
  let showCancel = true;

  if (conflict?.code === "pipeline_has_leads") {
    title = "В воронке есть лиды";
    body = (
      <p className="text-sm text-muted leading-relaxed">
        В воронке{" "}
        <span className="font-semibold text-ink">«{pipeline.name}»</span>{" "}
        находится <span className="font-mono">{conflict.lead_count}</span>{" "}
        лидов. Сначала переведите их в другую воронку или архивируйте.
      </p>
    );
    primaryLabel = "Понятно";
    primaryAction = onCancel;
    primaryStyle =
      "bg-ink text-white hover:bg-ink/90 active:scale-[0.98]";
    showCancel = false;
  } else if (conflict?.code === "pipeline_is_default") {
    title = "Это воронка по умолчанию";
    body = (
      <p className="text-sm text-muted leading-relaxed">
        Нельзя удалить воронку, назначенную основной. Сначала сделайте
        основной другую воронку, затем удалите эту.
      </p>
    );
    primaryLabel = "Понятно";
    primaryAction = onCancel;
    primaryStyle =
      "bg-ink text-white hover:bg-ink/90 active:scale-[0.98]";
    showCancel = false;
  } else {
    body = (
      <p className="text-sm text-muted leading-relaxed">
        Стадии будут удалены. Лиды останутся в системе, но потеряют связь
        с воронкой. Действие нельзя отменить.
      </p>
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={busy ? undefined : onCancel}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="alertdialog"
          aria-modal="true"
          aria-label={title}
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md p-6"
        >
          <h3 className="type-card-title text-ink mb-2">
            {title}
          </h3>
          {body}
          <div className="flex items-center justify-end gap-2 mt-5">
            {showCancel && (
              <button
                onClick={busy ? undefined : onCancel}
                disabled={busy}
                className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
              >
                Отмена
              </button>
            )}
            <button
              onClick={busy ? undefined : primaryAction}
              disabled={busy}
              className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-pill text-sm font-semibold disabled:opacity-40 transition-all duration-300 ${primaryStyle}`}
            >
              {busy && <Loader2 size={14} className="animate-spin" />}
              {primaryLabel}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
