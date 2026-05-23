"use client";

import { useMemo, useState } from "react";
import { CheckSquare, Square, Plus, Calendar, X, Loader2, Paperclip, Search, ChevronDown } from "lucide-react";
import { TaskFilesList } from "./TaskFilesList";
import { TaskFileDropzone } from "./TaskFileDropzone";
import {
  useLeadTasks,
  useCreateLeadTask,
  useCompleteLeadTask,
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

  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [due, setDue] = useState(""); // datetime-local: yyyy-mm-ddTHH:mm
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

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
    <div className="bg-white border border-brand-border rounded-[2rem] p-5 sm:p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="type-card-title text-brand-primary">Задачи</h2>
        {!adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 type-caption font-semibold ${C.button.pill}`}
          >
            <Plus size={13} /> Добавить задачу
          </button>
        )}
      </div>

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
        <p className={`type-body ${C.color.mutedLight} py-6 text-center`}>
          Задач нет
        </p>
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
              <li key={a.id} className="rounded-2xl bg-brand-bg overflow-hidden">
                <div className="flex items-start gap-3 px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => !a.task_done && completeTask.mutate(a.id)}
                    disabled={a.task_done || completeTask.isPending}
                    aria-label={a.task_done ? "Выполнено" : "Отметить выполненной"}
                    className="shrink-0 mt-0.5 text-brand-muted hover:text-brand-accent transition-colors disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded"
                  >
                    {a.task_done ? (
                      <CheckSquare size={16} className="text-success" />
                    ) : (
                      <Square size={16} />
                    )}
                  </button>
                  <div className="flex-1 min-w-0">
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
                  </div>
                  <button
                    type="button"
                    onClick={toggle}
                    aria-expanded={isExpanded}
                    aria-label="Файлы"
                    className="shrink-0 inline-flex items-center gap-1 type-caption text-brand-muted hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded"
                  >
                    <Paperclip size={12} />
                    <ChevronDown
                      size={12}
                      className={`transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    />
                  </button>
                </div>
                {isExpanded && (
                  <div className="px-3 pb-3 space-y-2 border-t border-brand-border/50 pt-2">
                    <TaskFilesList leadId={leadId} taskId={a.id} q={search.trim() || undefined} />
                    <TaskFileDropzone leadId={leadId} taskId={a.id} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
