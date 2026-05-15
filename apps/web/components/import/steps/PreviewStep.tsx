"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ListChecks,
  Loader2,
} from "lucide-react";

import { useApplyImport } from "@/lib/hooks/use-import";
import { ApiError } from "@/lib/api-client";
import type { ImportJobOut } from "@/lib/types";

const VISIBLE_ERRORS = 20;

interface Props {
  job: ImportJobOut;
  onBack: () => void;
  onApplied: (job: ImportJobOut) => void;
}

export function PreviewStep({ job, onBack, onApplied }: Props) {
  const stats = job.diff_json?.dry_run_stats;
  const willCreate = stats?.will_create ?? 0;
  const willSkip = stats?.will_skip ?? 0;
  const total = job.total_rows ?? willCreate + willSkip;

  const [showErrors, setShowErrors] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apply = useApplyImport();

  const flatErrors = stats?.errors
    ? Object.entries(stats.errors).flatMap(([row, msgs]) =>
        msgs.map((m) => ({ row: Number(row) + 1, msg: m })),
      )
    : [];

  function startApply() {
    setError(null);
    apply.mutate(job.id, {
      onSuccess: onApplied,
      onError: (err) => {
        const detail =
          err instanceof ApiError && typeof err.body === "object" && err.body
            ? (err.body as { detail?: unknown }).detail
            : null;
        setError(detail ? String(detail) : "Не удалось запустить импорт");
      },
    });
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-bold tracking-tight text-ink">
          Проверьте перед импортом
        </h3>
        <p className="text-[13px] text-muted mt-1">
          После запуска данные попадут в базу лидов. Это можно отменить только
          вручную — каждое сопоставление мы создадим как отдельную карточку.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <StatCard
          tone="success"
          icon={<CheckCircle2 size={16} />}
          label="Будет создано"
          value={willCreate}
          unit="карточек"
        />
        <StatCard
          tone="warning"
          icon={<AlertTriangle size={16} />}
          label="Будет пропущено"
          value={willSkip}
          unit="строк с ошибками"
        />
        <StatCard
          tone="neutral"
          icon={<ListChecks size={16} />}
          label="Всего в файле"
          value={total}
          unit="строк"
        />
      </div>

      {/* Errors */}
      {flatErrors.length > 0 && (
        <div className="rounded-2xl border border-black/5 bg-white">
          <button
            onClick={() => setShowErrors((v) => !v)}
            className="flex items-center justify-between w-full px-4 py-3 text-left"
          >
            <span className="text-sm font-bold text-ink">
              Показать ошибки
              <span className="ml-2 text-[11px] font-mono text-muted-2">
                {flatErrors.length}
              </span>
            </span>
            <ChevronDown
              size={14}
              className={`text-muted-2 transition-transform ${showErrors ? "rotate-180" : ""}`}
            />
          </button>
          {showErrors && (
            <div className="border-t border-black/5">
              <div className="grid grid-cols-[60px_1fr] text-[10px] font-mono uppercase tracking-wider text-muted-3 px-4 py-2 bg-canvas">
                <span>Строка</span>
                <span>Ошибка</span>
              </div>
              <div className="divide-y divide-black/5 max-h-[28vh] overflow-y-auto">
                {flatErrors.slice(0, VISIBLE_ERRORS).map((e, i) => (
                  <div
                    key={`${e.row}-${i}`}
                    className="grid grid-cols-[60px_1fr] items-start gap-3 px-4 py-2 text-[12px]"
                  >
                    <span className="font-mono text-muted-2">#{e.row}</span>
                    <span className="text-ink">{e.msg}</span>
                  </div>
                ))}
                {flatErrors.length > VISIBLE_ERRORS && (
                  <div className="px-4 py-2 text-[11px] font-mono text-muted-3">
                    …и ещё {flatErrors.length - VISIBLE_ERRORS}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="text-[13px] text-rose bg-rose/10 rounded-xl px-3 py-2.5">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={onBack}
          disabled={apply.isPending}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
        >
          <ChevronLeft size={14} />
          Назад к маппингу
        </button>
        <button
          onClick={startApply}
          disabled={willCreate === 0 || apply.isPending}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-brand-accent text-white text-sm font-semibold hover:bg-brand-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-300"
        >
          {apply.isPending && <Loader2 size={14} className="animate-spin" />}
          {apply.isPending
            ? "Запускаем…"
            : willCreate === 0
              ? "Нечего импортировать"
              : `Импортировать ${willCreate} ${pluralKartochka(willCreate)}`}
        </button>
      </div>
    </div>
  );
}

function pluralKartochka(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "карточек";
  if (mod10 === 1) return "карточку";
  if (mod10 >= 2 && mod10 <= 4) return "карточки";
  return "карточек";
}

function StatCard({
  tone,
  icon,
  label,
  value,
  unit,
}: {
  tone: "success" | "warning" | "neutral";
  icon: React.ReactNode;
  label: string;
  value: number;
  unit: string;
}) {
  const palette = {
    success: "bg-emerald-50 text-emerald-700 border-emerald-200/60",
    warning: "bg-amber-50 text-amber-800 border-amber-200/60",
    neutral: "bg-canvas text-ink border-black/5",
  }[tone];

  return (
    <div
      className={`rounded-2xl border ${palette} px-4 py-3.5 flex flex-col gap-1.5`}
    >
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider opacity-80">
        {icon}
        {label}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-3xl font-bold tracking-tight tabular-nums">
          {value}
        </span>
        <span className="text-[11px] opacity-70">{unit}</span>
      </div>
    </div>
  );
}
