"use client";

import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { clsx } from "clsx";

import { useImportJob } from "@/lib/hooks/use-import";
import type { ImportJobOut } from "@/lib/types";

interface Props {
  jobId: string;
  initialJob: ImportJobOut;
  onClose: () => void;
}

export function ProgressStep({ jobId, initialJob, onClose }: Props) {
  const router = useRouter();
  const query = useImportJob(jobId);
  const job = query.data ?? initialJob;

  const total = Math.max(job.total_rows, 1);
  const processed = Math.min(job.processed, total);
  const percent = Math.round((processed / total) * 100);

  const isRunning = job.status === "running";
  const isSucceeded = job.status === "succeeded";
  const isFailed = job.status === "failed";

  function goToPool() {
    router.push("/leads-pool");
    onClose();
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-extrabold tracking-tight text-ink">
          {isRunning && "Импорт выполняется"}
          {isSucceeded && "Импорт завершён"}
          {isFailed && "Импорт завершён с ошибками"}
        </h3>
        <p className="text-[13px] text-muted mt-1">
          {isRunning &&
            "Не закрывайте окно — мы создаём карточки одну за другой и обновляем счётчики каждые две секунды."}
          {(isSucceeded || isFailed) && "Можно перейти к базе лидов."}
        </p>
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between text-[12px] font-mono text-muted-2">
          <span>
            <span className="font-bold text-ink tabular-nums">{processed}</span>
            <span className="text-muted-3"> / </span>
            <span className="tabular-nums">{job.total_rows}</span>
          </span>
          <span className="text-muted-3 tabular-nums">{percent}%</span>
        </div>
        <div className="relative h-2 rounded-pill bg-canvas overflow-hidden">
          <div
            className={clsx(
              "absolute inset-y-0 left-0 transition-[width] duration-500 ease-out",
              isFailed ? "bg-red-500" : "bg-brand-accent",
            )}
            style={{ width: `${Math.max(percent, 2)}%` }}
            aria-hidden
          />
        </div>
      </div>

      {/* Counter row */}
      <div className="grid grid-cols-3 gap-3">
        <Counter label="Обработано" value={processed} tone="neutral" />
        <Counter label="Успешно" value={job.succeeded} tone="success" />
        <Counter label="Ошибок" value={job.failed} tone="warning" />
      </div>

      {/* Final-state banner */}
      {isSucceeded && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-2xl bg-emerald-50 text-emerald-800">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
          <div className="text-[13px] leading-relaxed">
            Импортировано{" "}
            <span className="font-bold tabular-nums">{job.succeeded}</span>{" "}
            {pluralKartochek(job.succeeded)}.
            {job.failed > 0 && (
              <span className="text-amber-800">
                {" "}
                {job.failed} строк пропущено — детали в журнале.
              </span>
            )}
          </div>
        </div>
      )}

      {isFailed && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-2xl bg-amber-50 text-amber-800">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div className="text-[13px] leading-relaxed">
            Импортировано{" "}
            <span className="font-bold tabular-nums">{job.succeeded}</span>,
            пропущено{" "}
            <span className="font-bold tabular-nums">{job.failed}</span>.
            {job.error_summary && (
              <div className="mt-1 text-[11px] font-mono opacity-80">
                {job.error_summary}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center justify-end pt-1">
        {isRunning && (
          <span className="inline-flex items-center gap-2 text-[12px] font-mono text-muted-2">
            <Loader2 size={14} className="animate-spin" />
            Опрашиваем сервер каждые 2 сек.
          </span>
        )}
        {isSucceeded && (
          <button
            onClick={goToPool}
            className="px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 transition-all duration-300"
          >
            Перейти к базе лидов
          </button>
        )}
        {isFailed && (
          <div className="flex items-center gap-2">
            <button
              onClick={goToPool}
              className="text-sm font-semibold text-muted hover:text-ink transition-colors"
            >
              К базе лидов
            </button>
            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 transition-all duration-300"
            >
              Закрыть
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function pluralKartochek(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "карточек";
  if (mod10 === 1) return "карточка";
  if (mod10 >= 2 && mod10 <= 4) return "карточки";
  return "карточек";
}

function Counter({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "warning" | "neutral";
}) {
  const valueColor = {
    success: "text-emerald-700",
    warning: value > 0 ? "text-amber-700" : "text-muted-3",
    neutral: "text-ink",
  }[tone];
  return (
    <div className="rounded-xl bg-canvas px-3 py-2.5 flex flex-col gap-0.5">
      <span className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
        {label}
      </span>
      <span className={`text-xl font-extrabold tabular-nums ${valueColor}`}>
        {value}
      </span>
    </div>
  );
}
