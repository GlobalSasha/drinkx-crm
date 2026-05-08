"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Check,
  Download,
  FileArchive,
  FileJson,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";

import { useCreateExport, useExportJob } from "@/lib/hooks/use-export";
import { ApiError } from "@/lib/api-client";
import type { ExportJobFormat } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Phase = "idle" | "loading" | "polling" | "done" | "error";

const FORMATS: {
  value: ExportJobFormat;
  label: string;
  hint: string;
  icon: React.ReactNode;
}[] = [
  { value: "xlsx", label: "Excel", hint: ".xlsx", icon: <FileSpreadsheet size={14} /> },
  { value: "csv", label: "CSV", hint: ".csv", icon: <FileText size={14} /> },
  { value: "json", label: "JSON", hint: ".json", icon: <FileJson size={14} /> },
  { value: "yaml", label: "YAML", hint: ".yaml", icon: <FileJson size={14} /> },
  { value: "md_zip", label: "Markdown ZIP", hint: ".zip · по карточке на лид", icon: <FileArchive size={14} /> },
];


interface Props {
  /** Filters to send with the export request. Same shape as GET /api/leads
   *  (subset accepted by backend). Pass {} to export everything in the
   *  workspace. */
  filters: Record<string, unknown>;
  /** Lead count for the "Область" caption. Falsy → don't render the count. */
  leadCount?: number;
  /** Optional class to override the trigger button styling. Defaults
   *  to the same secondary-tone pill the import button uses. */
  triggerClassName?: string;
  /** Optional label override; defaults to «Экспорт». */
  label?: string;
}

export function ExportPopover({
  filters,
  leadCount,
  triggerClassName,
  label = "Экспорт",
}: Props) {
  const [open, setOpen] = useState(false);
  const [format, setFormat] = useState<ExportJobFormat>("xlsx");
  const [includeAiBrief, setIncludeAiBrief] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorText, setErrorText] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const create = useCreateExport();
  const { data: job } = useExportJob(jobId);

  // Reset state every time the popover is opened — fresh attempt every
  // time, even after a previous done/error in the same session.
  useEffect(() => {
    if (open) {
      setPhase("idle");
      setErrorText(null);
      setJobId(null);
      // keep `format` and `includeAiBrief` as the manager last picked
    }
  }, [open]);

  // React to job status updates from the polling query.
  useEffect(() => {
    if (!job) return;
    if (job.status === "done") {
      setPhase("done");
      // Trigger browser download. Same-origin via /api/... so the
      // session cookie / Authorization header are reused.
      window.location.href = `${API_URL}/api/export/${job.id}/download`;
      // Auto-close 1.5s after triggering download — gives the click a
      // chance to register before the popover unmounts.
      const t = setTimeout(() => setOpen(false), 1500);
      return () => clearTimeout(t);
    }
    if (job.status === "failed") {
      setPhase("error");
      setErrorText(job.error || "Не удалось подготовить файл");
    }
    return undefined;
  }, [job]);

  // Click outside / Escape — close only when not in the middle of an
  // active export. Aborting an in-flight job from the UI is out of
  // scope for v1.
  useEffect(() => {
    if (!open) return;
    function onPointer(e: MouseEvent) {
      if (phase === "loading" || phase === "polling") return;
      const node = containerRef.current;
      if (!node) return;
      if (!node.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (phase === "loading" || phase === "polling") return;
      setOpen(false);
    }
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, phase]);

  function handleSubmit() {
    setErrorText(null);
    setPhase("loading");
    create.mutate(
      { format, filters, include_ai_brief: includeAiBrief },
      {
        onSuccess: (data) => {
          setJobId(data.id);
          setPhase("polling");
        },
        onError: (err) => {
          const detail =
            err instanceof ApiError && typeof err.body === "object" && err.body
              ? (err.body as { detail?: unknown }).detail
              : null;
          setErrorText(detail ? String(detail) : "Не удалось создать экспорт");
          setPhase("error");
        },
      },
    );
  }

  const busy = phase === "loading" || phase === "polling";
  const buttonLabel = useMemo(() => {
    if (phase === "loading") return "Создаём задачу…";
    if (phase === "polling") return "Готовим файл…";
    if (phase === "done") return "Готово";
    return "Экспортировать";
  }, [phase]);

  return (
    <div className="relative inline-block" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={clsx(
          triggerClassName ??
            "inline-flex items-center gap-1.5 bg-canvas text-ink border border-black/10 rounded-pill px-4 py-2 text-sm font-semibold transition-all duration-700 ease-soft hover:bg-canvas-2 hover:border-black/20 active:scale-[0.98]",
        )}
      >
        <Download size={14} />
        {label}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Экспорт лидов"
          className="absolute right-0 top-full mt-2 w-[20rem] sm:w-[22rem] bg-white rounded-2xl border border-black/5 shadow-soft p-4 z-30 max-w-[calc(100vw-2rem)]"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <div className="mb-3">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
              Экспорт лидов
            </div>
            <div className="text-sm font-bold text-ink mt-0.5">
              Выгрузить в файл
            </div>
          </div>

          {/* Format grid */}
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3 mb-1.5">
              Формат
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {FORMATS.map((f) => {
                const active = format === f.value;
                return (
                  <button
                    key={f.value}
                    type="button"
                    disabled={busy}
                    onClick={() => setFormat(f.value)}
                    className={clsx(
                      "flex items-start gap-2 rounded-xl border px-2.5 py-2 text-left transition-all duration-200 outline-none",
                      active
                        ? "border-accent bg-accent/5"
                        : "border-black/10 hover:border-black/20 hover:bg-canvas",
                      f.value === "md_zip" && "col-span-2",
                      busy && "opacity-50 cursor-not-allowed",
                    )}
                    aria-pressed={active}
                  >
                    <span
                      className={clsx(
                        "mt-0.5 shrink-0",
                        active ? "text-accent" : "text-muted-2",
                      )}
                    >
                      {f.icon}
                    </span>
                    <div className="min-w-0">
                      <div
                        className={clsx(
                          "text-[12px] font-semibold leading-snug",
                          active ? "text-ink" : "text-ink",
                        )}
                      >
                        {f.label}
                      </div>
                      <div className="text-[10px] font-mono text-muted-3 truncate">
                        {f.hint}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* AI Brief toggle */}
          <button
            type="button"
            disabled={busy || format === "md_zip"}
            onClick={() => setIncludeAiBrief((v) => !v)}
            className={clsx(
              "mt-3 flex items-center justify-between w-full rounded-xl px-3 py-2 transition-all",
              "bg-canvas hover:bg-canvas-2",
              busy && "opacity-50 cursor-not-allowed",
              format === "md_zip" && "opacity-60 cursor-not-allowed",
            )}
            aria-pressed={includeAiBrief}
          >
            <div className="text-left">
              <div className="text-[12px] font-semibold text-ink">
                Включить AI Brief
              </div>
              <div className="text-[10px] text-muted-2 leading-snug">
                {format === "md_zip"
                  ? "Markdown ZIP всегда содержит AI Brief"
                  : "Добавит колонку с кратким описанием компании"}
              </div>
            </div>
            <span
              className={clsx(
                "shrink-0 ml-2 w-9 h-5 rounded-pill relative transition-colors",
                includeAiBrief || format === "md_zip"
                  ? "bg-accent"
                  : "bg-black/15",
              )}
              aria-hidden
            >
              <span
                className={clsx(
                  "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform",
                  (includeAiBrief || format === "md_zip") &&
                    "translate-x-4",
                )}
              />
            </span>
          </button>

          {/* Scope */}
          <div className="mt-3 rounded-xl border border-black/5 px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
              Область
            </div>
            <div className="flex items-baseline justify-between mt-0.5">
              <div className="text-[12px] text-ink">Текущие фильтры</div>
              {typeof leadCount === "number" && (
                <div className="text-[11px] font-mono text-muted-2 tabular-nums">
                  {leadCount} {pluralLeads(leadCount)}
                </div>
              )}
            </div>
          </div>

          {/* Error inline */}
          {phase === "error" && errorText && (
            <div className="mt-3 flex items-start gap-2 text-[12px] text-red-700 bg-red-50 rounded-xl px-3 py-2">
              <AlertCircle size={13} className="shrink-0 mt-0.5" />
              <span>{errorText}</span>
            </div>
          )}

          {/* Footer */}
          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              className="text-[12px] font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={busy || phase === "done"}
              className={clsx(
                "inline-flex items-center gap-2 px-4 py-2 rounded-pill text-[12px] font-semibold transition-all duration-300",
                phase === "done"
                  ? "bg-emerald-600 text-white"
                  : "bg-accent text-white hover:bg-accent/90",
                "disabled:opacity-60 disabled:cursor-not-allowed",
              )}
            >
              {busy && <Loader2 size={13} className="animate-spin" />}
              {phase === "done" && <Check size={13} />}
              {buttonLabel}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function pluralLeads(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "лидов";
  if (mod10 === 1) return "лид";
  if (mod10 >= 2 && mod10 <= 4) return "лида";
  return "лидов";
}
