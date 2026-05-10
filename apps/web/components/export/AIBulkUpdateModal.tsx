"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  Copy,
  Download,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { clsx } from "clsx";

import { useBulkUpdatePrompt } from "@/lib/hooks/use-export";
import { downloadAuthed } from "@/lib/download";
import { ApiError } from "@/lib/api-client";
import { usePipelineStore } from "@/lib/store/pipeline-store";

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Three-step modal for the AI bulk-update flow (PRD §6.14):
 *
 *   1. Download leads_snapshot.yaml (authed download via /lib/download)
 *   2. Copy the canonical prompt from /api/export/bulk-update-prompt
 *   3. Hand off to the existing ImportWizard (Group 3) so the manager
 *      uploads the AI's response. The wizard is mounted globally in
 *      (app)/layout.tsx, so we just flip the pipeline-store flag.
 *
 *  No wizard-style stepper here — the three steps are small and live
 *  side-by-side with vertical spacing rather than progressive disclosure.
 *  Cleaner copy/paste loop for the manager, fewer clicks.
 */
export function AIBulkUpdateModal({ open, onClose }: Props) {
  const [snapshotPhase, setSnapshotPhase] =
    useState<"idle" | "loading" | "done" | "error">("idle");
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const { openImportWizard } = usePipelineStore();
  const promptQuery = useBulkUpdatePrompt(open);

  // Reset internal state every reopen — fresh attempt every time.
  useEffect(() => {
    if (open) {
      setSnapshotPhase("idle");
      setSnapshotError(null);
      setCopied(false);
    }
  }, [open]);

  // Esc to close.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function handleDownloadSnapshot() {
    setSnapshotError(null);
    setSnapshotPhase("loading");
    try {
      const date = new Date().toISOString().slice(0, 10);
      await downloadAuthed(
        "/api/export/snapshot?include_ai_brief=true",
        `leads_snapshot_${date}.yaml`,
      );
      setSnapshotPhase("done");
    } catch (err) {
      setSnapshotPhase("error");
      setSnapshotError(
        err instanceof ApiError
          ? `Не удалось скачать snapshot (${err.status})`
          : "Не удалось скачать snapshot",
      );
    }
  }

  async function handleCopyPrompt() {
    const text = promptQuery.data?.prompt ?? "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for environments without clipboard API: select the
      // textarea so the manager can Ctrl+C manually.
      promptRef.current?.select();
    }
  }

  function handleHandoff() {
    onClose();
    // Microtask so the AI modal exits before the wizard mounts —
    // avoids a flash of two stacked modals.
    setTimeout(() => openImportWizard(), 0);
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Обновление через AI"
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-black/5 flex items-start justify-between gap-4">
            <div className="min-w-0 flex items-start gap-2">
              <div className="w-8 h-8 rounded-xl bg-brand-soft text-brand-accent flex items-center justify-center shrink-0">
                <Sparkles size={16} />
              </div>
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
                  PRD §6.14
                </div>
                <h2 className="text-base font-extrabold tracking-tight text-ink mt-0.5">
                  Обновление через AI
                </h2>
              </div>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-muted-2 hover:bg-canvas hover:text-ink transition-colors"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="px-6 py-5 overflow-y-auto space-y-4">
            <Step
              n={1}
              title="Скачайте текущую базу"
              hint="YAML со всеми лидами и AI Brief'ом — формат под внешнюю модель."
            >
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDownloadSnapshot}
                  disabled={snapshotPhase === "loading"}
                  className={clsx(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-pill text-[12px] font-semibold transition-all duration-300",
                    snapshotPhase === "done"
                      ? "bg-emerald-600 text-white"
                      : "bg-ink text-white hover:bg-ink/90",
                    "disabled:opacity-60 disabled:cursor-not-allowed",
                  )}
                >
                  {snapshotPhase === "loading" && (
                    <Loader2 size={13} className="animate-spin" />
                  )}
                  {snapshotPhase === "done" ? (
                    <Check size={13} />
                  ) : (
                    <Download size={13} />
                  )}
                  {snapshotPhase === "loading" && "Готовим…"}
                  {snapshotPhase === "done" && "Скачано"}
                  {(snapshotPhase === "idle" || snapshotPhase === "error") &&
                    "Скачать snapshot"}
                </button>
                {snapshotPhase === "error" && snapshotError && (
                  <span className="text-[11px] text-red-700">
                    {snapshotError}
                  </span>
                )}
              </div>
            </Step>

            <Step
              n={2}
              title="Скопируйте промпт"
              hint="Вставьте snapshot и этот промпт в Claude / ChatGPT / Perplexity."
            >
              <textarea
                ref={promptRef}
                readOnly
                value={
                  promptQuery.isLoading
                    ? "Загружаем промпт…"
                    : promptQuery.data?.prompt ?? "Не удалось загрузить промпт"
                }
                rows={6}
                className="w-full text-[11px] font-mono leading-relaxed bg-canvas border border-black/10 rounded-xl p-3 outline-none focus:border-brand-accent/40 resize-none"
                onFocus={(e) => e.currentTarget.select()}
              />
              <div className="flex items-center justify-between mt-2">
                <span className="text-[10px] text-muted-3">
                  Кликните в поле — выделится весь текст.
                </span>
                <button
                  onClick={handleCopyPrompt}
                  disabled={!promptQuery.data?.prompt}
                  className={clsx(
                    "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-[11px] font-semibold transition-all",
                    copied
                      ? "bg-emerald-600 text-white"
                      : "bg-canvas text-ink border border-black/10 hover:bg-canvas-2",
                    "disabled:opacity-40 disabled:cursor-not-allowed",
                  )}
                >
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  {copied ? "Скопировано" : "Скопировать"}
                </button>
              </div>
            </Step>

            <Step
              n={3}
              title="Загрузите ответ AI"
              hint="После того как модель вернёт обновления — откроется обычный мастер импорта."
            >
              <button
                onClick={handleHandoff}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-pill bg-brand-accent text-white text-[12px] font-semibold hover:bg-brand-accent/90 transition-all duration-300"
              >
                Продолжить — загрузить файл
                <ArrowRight size={13} />
              </button>
            </Step>
          </div>
        </div>
      </div>
    </>
  );
}

function Step({
  n,
  title,
  hint,
  children,
}: {
  n: number;
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-black/5 bg-canvas/40 p-4">
      <div className="flex items-start gap-3">
        <span className="shrink-0 w-6 h-6 rounded-full bg-ink text-white text-[11px] font-bold flex items-center justify-center tabular-nums">
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-bold text-ink">{title}</div>
          <p className="text-[12px] text-muted-2 mt-0.5">{hint}</p>
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </div>
  );
}
