"use client";

import { useRef, useState } from "react";
import { Loader2, UploadCloud } from "lucide-react";
import {
  useApplyResolutions,
  useCreateIngestJob,
  useIngestJob,
  useIngestJobConflicts,
} from "@/lib/hooks/use-base-update";
import { ConflictCard } from "./base-update/ConflictCard";

const RUNNING = new Set<string>(["pending", "extracting", "matching", "resolving"]);

export function BaseUpdateSection() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const create = useCreateIngestJob();
  const job = useIngestJob(activeJobId);
  const conflicts = useIngestJobConflicts(activeJobId, true);
  const apply = useApplyResolutions(activeJobId);

  const status = job.data?.status;
  const stats = job.data?.stats_json ?? null;
  const running = !!status && RUNNING.has(status);
  const openConflicts = conflicts.data ?? [];

  function handleFiles(list: FileList | null) {
    if (!list) return;
    const arr = Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".md"));
    setPicked(arr);
  }

  async function handleUpload() {
    if (picked.length === 0 || create.isPending) return;
    const result = await create.mutateAsync(picked);
    setActiveJobId(result.id);
    setPicked([]);
  }

  function reset() {
    setActiveJobId(null);
    setPicked([]);
  }

  // ----- idle: no active job -----
  if (!activeJobId) {
    return (
      <section className="space-y-4">
        <header>
          <h2 className="type-section-title text-brand-primary">Обновление базы</h2>
          <p className="type-body text-brand-muted mt-1">
            Загрузите пачку <code>.md</code>-карточек ЛПР — CRM сама извлечёт компании,
            контакты и брифы, дополнит базу безопасным, а спорное вынесет на ваше ревью.
          </p>
        </header>

        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          className="cursor-pointer bg-white border-2 border-dashed border-brand-border rounded-card p-8 text-center hover:border-brand-accent transition-colors"
        >
          <UploadCloud size={28} className="text-brand-muted mx-auto mb-2" />
          <p className="type-body text-brand-primary">
            Перетащите .md-файлы сюда или нажмите, чтобы выбрать
          </p>
          <p className="type-caption text-brand-muted mt-1">
            Максимум 5 МБ суммарно. Принимаются только файлы с расширением .md.
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".md,text/markdown"
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {picked.length > 0 && (
          <div className="bg-brand-bg rounded-card p-4 space-y-2">
            <p className="type-caption text-brand-muted">Выбрано {picked.length} файл(а):</p>
            <ul className="space-y-1">
              {picked.map((f) => (
                <li key={f.name} className="type-body text-brand-primary truncate">
                  · {f.name}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={handleUpload}
              disabled={create.isPending}
              className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-full type-caption font-semibold bg-brand-accent text-white hover:bg-brand-accent/90 disabled:opacity-40"
            >
              {create.isPending && <Loader2 size={14} className="animate-spin" />}
              Загрузить и разобрать
            </button>
          </div>
        )}

        {create.isError && (
          <p className="type-caption text-rose">{(create.error as Error).message}</p>
        )}
      </section>
    );
  }

  // ----- running -----
  if (running) {
    return (
      <section className="space-y-4">
        <header className="flex items-center gap-2">
          <Loader2 size={18} className="animate-spin text-brand-accent" />
          <h2 className="type-section-title text-brand-primary">Обработка…</h2>
        </header>
        <p className="type-body text-brand-muted">
          Статус: {status}
          {stats?.files !== undefined && ` · файлов: ${stats.files}`}
        </p>
      </section>
    );
  }

  // ----- ready / resolving / done -----
  const done = status === "done";
  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <h2 className="type-section-title text-brand-primary">
          {done ? "Готово" : "Сводка и конфликты"}
        </h2>
        <button
          type="button"
          onClick={reset}
          className="px-3 py-1.5 rounded-full type-caption font-semibold bg-brand-bg text-brand-primary hover:bg-brand-panel"
        >
          {done ? "Загрузить ещё" : "Закрыть"}
        </button>
      </header>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Создано лидов" value={(stats.records_created ?? 0) as number} />
          <Stat label="Дополнено" value={(stats.records_updated ?? 0) as number} />
          <Stat label="С конфликтами" value={(stats.records_conflict ?? 0) as number} />
          <Stat label="Конфликтов всего" value={(stats.conflicts_total ?? 0) as number} />
        </div>
      )}

      {job.data?.error && (
        <p className="type-caption text-rose">Замечание: {job.data.error}</p>
      )}

      {!done && (
        <div className="space-y-3">
          <h3 className="type-card-title text-brand-primary">
            Открытых конфликтов: {openConflicts.length}
          </h3>
          {openConflicts.length === 0 ? (
            <p className="type-body text-brand-muted">Всё решено. Можно применить.</p>
          ) : (
            <div className="space-y-3">
              {openConflicts.map((cf) => (
                <ConflictCard key={cf.id} jobId={activeJobId} conflict={cf} />
              ))}
            </div>
          )}
          <button
            type="button"
            disabled={openConflicts.length > 0 || apply.isPending}
            onClick={() => apply.mutate()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full type-caption font-semibold bg-brand-accent text-white hover:bg-brand-accent/90 disabled:opacity-40"
          >
            {apply.isPending && <Loader2 size={14} className="animate-spin" />}
            Применить решения
          </button>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white border border-brand-border rounded-card p-3">
      <div className="type-caption text-brand-muted">{label}</div>
      <div className="type-card-title text-brand-primary tabular-nums">{value}</div>
    </div>
  );
}
