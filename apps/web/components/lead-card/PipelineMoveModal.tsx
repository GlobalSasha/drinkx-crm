"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";

import { Modal } from "@/components/ui/Modal";
import { apiErrorDetail } from "@/lib/api-error";
import { C } from "@/lib/design-system";
import { useChangeLeadPipeline } from "@/lib/hooks/use-lead-v2";
import { usePipelines } from "@/lib/hooks/use-pipelines";

interface Props {
  leadId: string;
  currentPipelineId: string | null;
  currentStageId: string | null;
  onClose: () => void;
  onSuccess?: () => void;
}

export function PipelineMoveModal({
  leadId,
  currentPipelineId,
  currentStageId,
  onClose,
  onSuccess,
}: Props) {
  const pipelinesQuery = usePipelines();
  const changePipeline = useChangeLeadPipeline(leadId);

  const [pipelineId, setPipelineId] = useState<string | null>(currentPipelineId);
  const [stageId, setStageId] = useState<string | null>(currentStageId);
  const [error, setError] = useState<string | null>(null);

  const pipelines = pipelinesQuery.data ?? [];
  const selectedPipeline = pipelines.find((p) => p.id === pipelineId) ?? null;
  // Победа и отказ из списка убраны: перенос между воронками — не способ
  // закрыть сделку. Закрытие идёт своей кнопкой в шапке карточки, оно
  // требует причины отказа.
  const stages = selectedPipeline
    ? [...selectedPipeline.stages]
        .filter((st) => !st.is_won && !st.is_lost)
        .sort((a, b) => a.position - b.position)
    : [];

  const isSameTarget =
    pipelineId === currentPipelineId && stageId === currentStageId;
  const canSubmit =
    Boolean(pipelineId) && Boolean(stageId) && !isSameTarget && !changePipeline.isPending;

  const handlePipelineChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextPipelineId = event.target.value;
    setPipelineId(nextPipelineId);

    const nextPipeline = pipelines.find((p) => p.id === nextPipelineId);
    const firstStage = nextPipeline
      ? [...nextPipeline.stages]
          .filter((st) => !st.is_won && !st.is_lost)
          .sort((a, b) => a.position - b.position)[0]
      : undefined;
    setStageId(firstStage ? firstStage.id : null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit || !pipelineId || !stageId) return;

    setError(null);
    try {
      await changePipeline.mutateAsync({ pipeline_id: pipelineId, stage_id: stageId });
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(apiErrorDetail(err, "Не удалось перенести лид"));
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Перенести в другую воронку"
      size="max-w-md"
      dismissOnBackdrop={false}
    >
      <form onSubmit={handleSubmit} className="-m-6 p-6 max-h-[90vh] overflow-y-auto">
        <h3 className="text-base font-bold">Перенести в другую воронку</h3>
        <p className="mt-1 text-xs text-brand-muted">
          Выберите воронку и этап, на который встанет лид.
        </p>

        <div className="mt-4">
          {pipelinesQuery.isLoading ? (
            <p className="text-sm text-brand-muted">Загружаем воронки…</p>
          ) : (
            <>
              <div className="mb-3">
                <label
                  htmlFor="pipeline-move-pipeline"
                  className="block font-mono text-2xs uppercase tracking-[0.12em] text-brand-muted mb-1.5"
                >
                  Воронка
                </label>
                <select
                  id="pipeline-move-pipeline"
                  className={C.form.field}
                  value={pipelineId ?? ""}
                  onChange={handlePipelineChange}
                >
                  <option value="" disabled>
                    Выберите воронку
                  </option>
                  {pipelines.map((pipeline) => (
                    <option key={pipeline.id} value={pipeline.id}>
                      {pipeline.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="mb-3">
                <label
                  htmlFor="pipeline-move-stage"
                  className="block font-mono text-2xs uppercase tracking-[0.12em] text-brand-muted mb-1.5"
                >
                  Этап
                </label>
                <select
                  id="pipeline-move-stage"
                  className={C.form.field}
                  value={stageId ?? ""}
                  onChange={(event) => setStageId(event.target.value)}
                  disabled={stages.length === 0}
                >
                  {stages.length === 0 ? (
                    <option value="">—</option>
                  ) : (
                    stages.map((stage) => (
                      <option key={stage.id} value={stage.id}>
                        {stage.name}
                      </option>
                    ))
                  )}
                </select>
              </div>

              {selectedPipeline && stages.length === 0 && (
                <p className="mb-3 text-xs text-brand-muted">В этой воронке нет подходящих этапов</p>
              )}

              <p className="mb-3 text-xs text-brand-muted">
                Лид уйдёт из текущей воронки и появится в выбранной на указанном этапе. Заметки,
                задачи, контакты и переписка останутся при нём.
              </p>
            </>
          )}
        </div>

        {error && (
          <div className="mb-3 flex items-start gap-2 bg-rose/5 border border-rose/20 rounded-xl px-3 py-2">
            <p className="text-xs text-rose">{error}</p>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-full text-sm font-semibold text-brand-muted bg-brand-bg hover:bg-brand-panel transition"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 px-5 py-2 rounded-full text-sm font-semibold bg-brand-accent text-white transition hover:bg-brand-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {changePipeline.isPending ? "…" : "Перенести"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
