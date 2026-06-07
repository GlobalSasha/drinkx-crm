"use client";

import { useMemo, useState } from "react";
import { CheckSquare, Square, Plus, Calendar, X, Loader2, Paperclip, Search, ChevronDown, Pencil, ListChecks, Trash2 } from "lucide-react";
import { InlineConfirm } from "@/components/ui/InlineConfirm";
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/Empty";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Item, ItemContent, ItemActions } from "@/components/ui/Item";
import { TaskFilesList } from "./TaskFilesList";
import { TaskFileDropzone } from "./TaskFileDropzone";
import { TaskEditModal } from "@/components/tasks/TaskEditModal";
import {
  useLeadTasks,
  useCreateLeadTask,
  useCompleteLeadTask,
  useReopenLeadTask,
  useArchiveLeadTask,
} from "@/lib/hooks/use-lead-tasks";
import { C } from "@/lib/design-system";
import type { ActivityOut } from "@/lib/types";

interface Props {
  leadId: string;
}

function taskTitle(a: ActivityOut): string {
  return (a.payload_json?.title as string | undefined) ?? a.body ?? "Задача";
}

function formatDue(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const date = d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  return `${date}, ${time}`;
}

// Manager-entered tasks only — no follow-ups, no AI. The manager sets
// text and due date.
export function TasksTab({ leadId }: Props) {
  const { data: tasks, isLoading, isError } = useLeadTasks(leadId);
  const createTask = useCreateLeadTask(leadId);
  const completeTask = useCompleteLeadTask(leadId);
  const reopenTask = useReopenLeadTask(leadId);
  const archiveTask = useArchiveLeadTask(leadId);

  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [due, setDue] = useState(""); // datetime-local: yyyy-mm-ddTHH:mm
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [editingTask, setEditingTask] = useState<ActivityOut | null>(null);

  // Open first, then by due date ascending (nulls last).
  const rows = useMemo(() => {
    const sorted = [...(tasks ?? [])].sort((a, b) => {
      if (a.task_done !== b.task_done) return a.task_done ? 1 : -1;
      const ad = a.task_due_at ? new Date(a.task_due_at).getTime() : Infinity;
      const bd = b.task_due_at ? new Date(b.task_due_at).getTime() : Infinity;
      return ad - bd;
    });
    const q = search.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((a) => {
      const title = taskTitle(a).toLowerCase();
      const body = (a.body ?? "").toLowerCase();
      return title.includes(q) || body.includes(q);
    });
  }, [tasks, search]);

  function handleSubmit() {
    const t = text.trim();
    if (!t || createTask.isPending) return;
    let iso: string | null = null;
    if (due) {
      const d = new Date(due); // datetime-local is parsed in local time
      if (!Number.isNaN(d.getTime())) iso = d.toISOString();
    }
    createTask.mutate(
      { text: t, task_due_at: iso },
      {
        onSuccess: () => {
          setText("");
          setDue("");
          setAdding(false);
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Задачи</CardTitle>
        {!adding && (
          <Button variant="pill" size="sm" type="button" onClick={() => setAdding(true)}>
            <Plus size={13} /> Добавить задачу
          </Button>
        )}
      </CardHeader>

      <div className="mb-3 relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-brand-muted pointer-events-none" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по задачам и файлам"
          className={`w-full pl-8 pr-3 py-2 ${C.form.field}`}
        />
      </div>

      {adding && (
        <div className="mb-4 flex flex-col sm:flex-row gap-2 sm:items-center">
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && text.trim()) handleSubmit();
              if (e.key === "Escape") {
                setAdding(false);
                setText("");
                setDue("");
              }
            }}
            placeholder="Название задачи…"
            disabled={createTask.isPending}
            className={`flex-1 ${C.form.field}`}
          />
          <input
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            disabled={createTask.isPending}
            aria-label="Срок и время"
            className={`${C.form.field} sm:w-56`}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!text.trim() || createTask.isPending}
              className={`${C.button.primary} type-body px-4 py-2.5 disabled:opacity-40`}
            >
              {createTask.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                "Сохранить"
              )}
            </button>
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setText("");
                setDue("");
              }}
              aria-label="Отменить"
              className={`${C.button.ghost} type-body px-3 py-2.5`}
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 py-6 justify-center text-brand-muted">
          <Loader2 size={16} className="animate-spin" />
          <span className="type-caption">Загрузка…</span>
        </div>
      )}

      {!isLoading && isError && (
        <p className="type-caption text-rose py-4">Не удалось загрузить задачи</p>
      )}

      {!isLoading && !isError && rows.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><ListChecks /></EmptyMedia>
            <EmptyTitle>{search.trim() ? "Ничего не найдено" : "Задач пока нет"}</EmptyTitle>
            <EmptyDescription>
              {search.trim()
                ? "Попробуйте другой запрос или очистите поиск."
                : "Поставьте первую задачу через кнопку «+ Добавить задачу»."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}

      {!isLoading && !isError && rows.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {rows.map((a) => {
            const dueLabel = formatDue(a.task_due_at);
            const isExpanded = expanded.has(a.id);
            const toggle = () =>
              setExpanded((s) => {
                const n = new Set(s);
                if (n.has(a.id)) n.delete(a.id);
                else n.add(a.id);
                return n;
              });
            return (
              <li key={a.id} className="rounded-card bg-brand-bg overflow-hidden">
                <Item variant="inline" className="px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() =>
                      a.task_done
                        ? reopenTask.mutate(a.id)
                        : completeTask.mutate(a.id)
                    }
                    disabled={completeTask.isPending || reopenTask.isPending}
                    aria-label={a.task_done ? "Вернуть в активные" : "Отметить выполненной"}
                    title={a.task_done ? "Вернуть в активные" : "Отметить выполненной"}
                    className="shrink-0 mt-0.5 text-brand-muted hover:text-brand-accent transition-colors disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded"
                  >
                    {a.task_done ? (
                      <CheckSquare size={16} className="text-success" />
                    ) : (
                      <Square size={16} />
                    )}
                  </button>
                  <ItemContent>
                    <p
                      className={`type-body ${
                        a.task_done ? "line-through text-brand-muted" : "text-brand-primary"
                      }`}
                    >
                      {taskTitle(a)}
                    </p>
                    {dueLabel && (
                      <span className="inline-flex items-center gap-1 type-caption text-brand-muted mt-0.5">
                        <Calendar size={11} /> до {dueLabel}
                      </span>
                    )}
                  </ItemContent>
                  <ItemActions>
                    <button
                      type="button"
                      onClick={() => setEditingTask(a)}
                      aria-label="Редактировать задачу"
                      title="Редактировать задачу"
                      className="inline-flex items-center justify-center w-8 h-8 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-muted hover:text-brand-primary hover:border-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      type="button"
                      onClick={toggle}
                      aria-expanded={isExpanded}
                      aria-label={isExpanded ? "Скрыть детали" : "Показать детали и файлы"}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-muted hover:text-brand-primary hover:border-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                    >
                      <Paperclip size={13} />
                      <ChevronDown
                        size={13}
                        className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </button>
                  </ItemActions>
                </Item>
                {isExpanded && (
                  <div className="px-3 pb-3 border-t border-brand-border/50 pt-3 space-y-4">
                    <div className="space-y-2">
                      <h4 className="type-caption text-brand-muted uppercase tracking-wide">Файлы</h4>
                      <TaskFilesList leadId={leadId} taskId={a.id} q={search.trim() || undefined} />
                      <TaskFileDropzone leadId={leadId} taskId={a.id} />
                    </div>
                    <div className="flex flex-wrap gap-2 border-t border-brand-border/50 pt-3">
                      <button
                        type="button"
                        onClick={() => setEditingTask(a)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-primary hover:border-brand-accent transition-colors"
                      >
                        <Pencil size={12} /> Изменить
                      </button>
                      <InlineConfirm
                        destructive
                        prompt="Переместить в архив?"
                        confirmLabel="Да, в архив"
                        busy={archiveTask.isPending}
                        onConfirm={() => archiveTask.mutate(a.id)}
                      >
                        {(openConfirm) => (
                          <button
                            type="button"
                            onClick={openConfirm}
                            disabled={archiveTask.isPending}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold text-rose bg-rose/10 hover:bg-rose/15 disabled:opacity-40 transition-colors"
                          >
                            <Trash2 size={12} /> В архив
                          </button>
                        )}
                      </InlineConfirm>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {editingTask && (
        <TaskEditModal
          leadId={leadId}
          taskId={editingTask.id}
          initialTitle={taskTitle(editingTask)}
          initialDueIso={editingTask.task_due_at}
          onClose={() => setEditingTask(null)}
        />
      )}
    </Card>
  );
}
