"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { clsx } from "clsx";

import type { ImportJobOut } from "@/lib/types";
import { UploadStep } from "@/components/import/steps/UploadStep";
import { MappingStep } from "@/components/import/steps/MappingStep";
import { PreviewStep } from "@/components/import/steps/PreviewStep";
import { ProgressStep } from "@/components/import/steps/ProgressStep";
import { BulkUpdatePreview } from "@/components/import/steps/BulkUpdatePreview";

type Step = 1 | 2 | 3 | 4;

const STEP_LABELS: Record<Step, string> = {
  1: "Загрузка",
  2: "Сопоставление",
  3: "Проверка",
  4: "Импорт",
};

function isBulkUpdateJob(job: ImportJobOut | null): boolean {
  return (job?.diff_json as { type?: string } | null)?.type === "bulk_update";
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ImportWizard({ open, onClose }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [job, setJob] = useState<ImportJobOut | null>(null);

  // Reset wizard state every time it's reopened — fresh attempt every time.
  useEffect(() => {
    if (open) {
      setStep(1);
      setJob(null);
    }
  }, [open]);

  // Esc to close — but only when not actively running an apply.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        attemptClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step, job?.status]);

  if (!open) return null;

  function attemptClose() {
    // Step 4 with status === 'running' → prompt before closing; the
    // import keeps going server-side either way, but we want the manager
    // to know they're walking away from progress visibility.
    if (step === 4 && job?.status === "running") {
      const confirmed = window.confirm(
        "Импорт ещё идёт. Закрыть окно? Импорт продолжится на сервере, а статус можно будет проверить в журнале.",
      );
      if (!confirmed) return;
    }
    onClose();
  }

  function onBackdropClick() {
    // Block backdrop close while a job is running — too easy to fat-finger.
    if (step === 4) return;
    attemptClose();
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={onBackdropClick}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Импорт лидов"
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-3xl max-h-[92vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-black/5 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
                Импорт лидов
              </div>
              <h2 className="text-lg font-extrabold tracking-tight text-ink mt-0.5">
                {STEP_LABELS[step]}
              </h2>
            </div>
            <button
              onClick={attemptClose}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-muted-2 hover:bg-canvas hover:text-ink transition-colors"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          {/* Step indicator. Bulk-update flow skips «Сопоставление». */}
          <Stepper current={step} isBulkUpdate={isBulkUpdateJob(job)} />

          {/* Body — scroll its own area, not the whole modal */}
          <div className="px-6 py-5 overflow-y-auto">
            {step === 1 && (
              <UploadStep
                onUploaded={(j) => {
                  setJob(j);
                  // bulk_update has no column-mapping step — server
                  // already returns status='previewed' with the
                  // computed diff. Skip directly to step 3.
                  setStep(isBulkUpdateJob(j) ? 3 : 2);
                }}
              />
            )}
            {step === 2 && job && (
              <MappingStep
                job={job}
                onBack={() => setStep(1)}
                onConfirmed={(j) => {
                  setJob(j);
                  setStep(3);
                }}
              />
            )}
            {step === 3 && job && isBulkUpdateJob(job) && (
              <BulkUpdatePreview
                job={job}
                onClose={onClose}
                onApplied={(j) => {
                  setJob(j);
                  setStep(4);
                }}
              />
            )}
            {step === 3 && job && !isBulkUpdateJob(job) && (
              <PreviewStep
                job={job}
                onBack={() => setStep(2)}
                onApplied={(j) => {
                  setJob(j);
                  setStep(4);
                }}
              />
            )}
            {step === 4 && job && (
              <ProgressStep
                jobId={job.id}
                initialJob={job}
                onClose={onClose}
              />
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Stepper({
  current,
  isBulkUpdate,
}: {
  current: Step;
  isBulkUpdate: boolean;
}) {
  const items: Step[] = isBulkUpdate ? [1, 3, 4] : [1, 2, 3, 4];
  return (
    <div className="px-6 py-3 border-b border-black/5 bg-canvas/40">
      <ol className="flex items-center gap-2">
        {items.map((n, i) => {
          const state =
            n < current ? "done" : n === current ? "current" : "upcoming";
          // Display the visual position (1, 2, 3, …) rather than the
          // raw step index so the bulk_update flow reads 1/2/3 instead
          // of 1/3/4 with the gap.
          const displayNumber = i + 1;
          return (
            <li key={n} className="flex items-center gap-2 flex-1 min-w-0">
              <span
                className={clsx(
                  "shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold tabular-nums transition-colors",
                  state === "done" && "bg-emerald-500 text-white",
                  state === "current" && "bg-accent text-white",
                  state === "upcoming" && "bg-canvas text-muted-3 border border-black/10",
                )}
                aria-current={state === "current" ? "step" : undefined}
              >
                {displayNumber}
              </span>
              <span
                className={clsx(
                  "text-[11px] font-semibold truncate hidden sm:inline",
                  state === "current" ? "text-ink" : "text-muted-3",
                )}
              >
                {STEP_LABELS[n]}
              </span>
              {i < items.length - 1 && (
                <span
                  className={clsx(
                    "h-px flex-1 transition-colors",
                    n < current ? "bg-emerald-500/40" : "bg-black/10",
                  )}
                  aria-hidden
                />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
