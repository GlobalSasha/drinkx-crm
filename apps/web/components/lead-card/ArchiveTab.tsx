"use client";

import { useMemo, useState } from "react";
import { Archive as ArchiveIcon, Calendar, CheckSquare, ChevronDown, Loader2, Paperclip, Square, Undo2 } from "lucide-react";
import { useLeadArchive, useRestoreLeadTask } from "@/lib/hooks/use-lead-tasks";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import type { ActivityOut } from "@/lib/types";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";
import { TaskFilesList } from "./TaskFilesList";

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
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const rows = useMemo(
    () => (archive.data?.items ?? []).filter((a) => a.type === "task"),
    [archive.data],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Архив задач</CardTitle>
      </CardHeader>

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
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><ArchiveIcon /></EmptyMedia>
            <EmptyTitle>Архив пуст</EmptyTitle>
            <EmptyDescription>
              Перемещённые сюда задачи сохраняются по лиду — вместе с прикреплёнными файлами и историей.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {!archive.isLoading && !archive.isError && rows.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {rows.map((a) => {
            const archivedLabel = fmtArchived(a.archived_at);
            const isExpanded = expanded.has(a.id);
            const toggle = () =>
              setExpanded((s) => {
                const n = new Set(s);
                if (n.has(a.id)) n.delete(a.id);
                else n.add(a.id);
                return n;
              });
            return (
              <li
                key={a.id}
                className="rounded-2xl bg-brand-bg overflow-hidden"
              >
                <div className="flex items-start gap-3 px-3 py-2.5">
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
                  <div className="shrink-0 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={toggle}
                      aria-expanded={isExpanded}
                      aria-label={isExpanded ? "Скрыть файлы" : "Показать файлы"}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-muted hover:text-brand-primary hover:border-brand-accent transition-colors"
                    >
                      <Paperclip size={13} />
                      <ChevronDown
                        size={13}
                        className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </button>
                    <button
                      type="button"
                      onClick={() => restore.mutate(a.id)}
                      disabled={restore.isPending}
                      aria-label="Восстановить из архива"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-primary hover:border-brand-accent transition-colors disabled:opacity-40"
                    >
                      <Undo2 size={12} /> Восстановить
                    </button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="px-3 pb-3 pt-2 border-t border-brand-border/50">
                    <TaskFilesList leadId={leadId} taskId={a.id} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
