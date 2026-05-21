"use client";

import { useMemo, useState } from "react";
import {
  CheckSquare,
  Square,
  Plus,
  Calendar,
  X,
  Loader2,
} from "lucide-react";
import {
  useLeadTasks,
  useCreateLeadTask,
  useCompleteLeadTask,
} from "@/lib/hooks/use-lead-tasks";
import { useFollowups, useCompleteFollowup } from "@/lib/hooks/use-followups";
import { C } from "@/lib/design-system";
import type { ActivityOut, FollowupOut } from "@/lib/types";

interface Props {
  leadId: string;
}

// Unified row model so tasks (Activity) and followups render in one list.
interface Row {
  id: string;
  kind: "task" | "followup";
  title: string;
  due: string | null;
  done: boolean;
}

function taskTitle(a: ActivityOut): string {
  return (
    (a.payload_json?.title as string | undefined) ?? a.body ?? "Задача"
  );
}

function formatDue(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
}

export function TasksTab({ leadId }: Props) {
  const tasksQuery = useLeadTasks(leadId);
  const { data: followups = [], isLoading: followupsLoading } =
    useFollowups(leadId);

  const createTask = useCreateLeadTask(leadId);
  const completeTask = useCompleteLeadTask(leadId);
  const completeFollowup = useCompleteFollowup(leadId);

  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [due, setDue] = useState(""); // yyyy-mm-dd

  const isLoading = tasksQuery.isLoading || followupsLoading;
  const isError = tasksQuery.isError;

  const rows: Row[] = useMemo(() => {
    const taskRows: Row[] = (tasksQuery.data ?? []).map((a: ActivityOut) => ({
      id: a.id,
      kind: "task",
      title: taskTitle(a),
      due: a.task_due_at,
      done: a.task_done,
    }));
    const fuRows: Row[] = (followups as FollowupOut[]).map((f) => ({
      id: f.id,
      kind: "followup",
      title: f.name,
      due: f.due_at,
      // status strings are inconsistent across the codebase — treat
      // completed_at as the source of truth for "done".
      done: f.completed_at != null,
    }));
    const all = [...taskRows, ...fuRows];
    // Open first, then by due date ascending (nulls last).
    return all.sort((a, b) => {
      if (a.done !== b.done) return a.done ? 1 : -1;
      const ad = a.due ? new Date(a.due).getTime() : Infinity;
      const bd = b.due ? new Date(b.due).getTime() : Infinity;
      return ad - bd;
    });
  }, [tasksQuery.data, followups]);

  function handleComplete(row: Row) {
    if (row.done) return;
    if (row.kind === "task") completeTask.mutate(row.id);
    else completeFollowup.mutate(row.id);
  }

  function handleSubmit() {
    const t = text.trim();
    if (!t || createTask.isPending) return;
    // Snap a date-only value to end-of-day, matching FeedComposer.
    let iso: string | null = null;
    if (due) {
      const d = new Date(due);
      d.setHours(23, 59, 0, 0);
      iso = d.toISOString();
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

      {/* Inline add form */}
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
            type="date"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            disabled={createTask.isPending}
            className={`${C.form.field} sm:w-44`}
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

      {/* List */}
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
          {rows.map((row) => {
            const busy =
              row.kind === "task"
                ? completeTask.isPending
                : completeFollowup.isPending;
            const dueLabel = formatDue(row.due);
            return (
              <li
                key={`${row.kind}-${row.id}`}
                className="flex items-start gap-3 px-3 py-2.5 rounded-2xl bg-brand-bg"
              >
                <button
                  type="button"
                  onClick={() => handleComplete(row)}
                  disabled={row.done || busy}
                  aria-label={
                    row.done ? "Выполнено" : "Отметить выполненной"
                  }
                  className="shrink-0 mt-0.5 text-brand-muted hover:text-brand-accent transition-colors disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 rounded"
                >
                  {row.done ? (
                    <CheckSquare size={16} className="text-success" />
                  ) : (
                    <Square size={16} />
                  )}
                </button>
                <div className="flex-1 min-w-0">
                  <p
                    className={`type-body ${
                      row.done
                        ? "line-through text-brand-muted"
                        : "text-brand-primary"
                    }`}
                  >
                    {row.title}
                  </p>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span
                      className={`type-caption font-semibold uppercase tracking-wide ${
                        row.kind === "task"
                          ? "text-brand-accent-text"
                          : "text-brand-muted"
                      }`}
                    >
                      {row.kind === "task" ? "Задача" : "Follow-up"}
                    </span>
                    {dueLabel && (
                      <span className="inline-flex items-center gap-1 type-caption text-brand-muted">
                        <Calendar size={11} /> до {dueLabel}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
