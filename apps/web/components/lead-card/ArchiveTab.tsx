"use client";

import { useMemo } from "react";
import { Calendar, CheckSquare, Loader2, Square, Undo2 } from "lucide-react";
import { useLeadArchive, useRestoreLeadTask } from "@/lib/hooks/use-lead-tasks";
import { C } from "@/lib/design-system";
import type { ActivityOut } from "@/lib/types";

interface Props {
  leadId: string;
}

function title(a: ActivityOut): string {
  return (a.payload_json?.title as string | undefined) ?? a.body ?? "Задача";
}

function fmtArchived(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function ArchiveTab({ leadId }: Props) {
  const archive = useLeadArchive(leadId);
  const restore = useRestoreLeadTask(leadId);

  const rows = useMemo(
    () => (archive.data?.items ?? []).filter((a) => a.type === "task"),
    [archive.data],
  );

  return (
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 sm:p-6">
      <h2 className="type-card-title text-brand-primary mb-4">Архив задач</h2>

      {archive.isLoading && (
        <div className="flex items-center gap-2 py-6 justify-center text-brand-muted">
          <Loader2 size={16} className="animate-spin" />
          <span className="type-caption">Загрузка…</span>
        </div>
      )}

      {!archive.isLoading && archive.isError && (
        <p className="type-caption text-rose py-4">Не удалось загрузить архив</p>
      )}

      {!archive.isLoading && !archive.isError && rows.length === 0 && (
        <p className={`type-body ${C.color.mutedLight} py-6 text-center`}>
          Архив пуст. Перемещённые сюда задачи сохраняются по лиду — вместе с
          прикреплёнными файлами и историей.
        </p>
      )}

      {!archive.isLoading && !archive.isError && rows.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {rows.map((a) => {
            const archivedLabel = fmtArchived(a.archived_at);
            return (
              <li
                key={a.id}
                className="flex items-start gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg"
              >
                <span className="shrink-0 mt-0.5 text-brand-muted">
                  {a.task_done ? <CheckSquare size={16} /> : <Square size={16} />}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="type-body text-brand-primary truncate">{title(a)}</p>
                  {archivedLabel && (
                    <span className="inline-flex items-center gap-1 type-caption text-brand-muted mt-0.5">
                      <Calendar size={11} /> в архиве с {archivedLabel}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => restore.mutate(a.id)}
                  disabled={restore.isPending}
                  aria-label="Восстановить из архива"
                  className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-primary hover:border-brand-accent transition-colors disabled:opacity-40"
                >
                  <Undo2 size={12} /> Восстановить
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
