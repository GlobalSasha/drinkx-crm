"use client";

// /tasks — full task list, opened from the ↗ on the Today widget.
//
// Manager-entered tasks only (no AI). Fed by GET /me/tasks — all
// Activity(type=task) across the user's leads, with their own due dates.

import { useMemo, useState } from "react";
import { ListChecks } from "lucide-react";
import { useMyTasks, useCompleteMyTask } from "@/lib/hooks/use-my-tasks";
import { TaskTable } from "@/components/tasks/TaskTable";
import {
  myTaskToRow,
  isOverdue,
  isToday,
  withinThisWeek,
  type TaskRow,
} from "@/lib/tasks";
import { C } from "@/lib/design-system";

type StatusFilter = "open" | "done" | "overdue";
type DateFilter = "today" | "week" | "all";

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full type-caption font-semibold transition-colors ${
        active
          ? "bg-brand-accent text-white"
          : "bg-brand-panel text-brand-muted-strong hover:bg-brand-border"
      }`}
    >
      {children}
    </button>
  );
}

export default function TasksPage() {
  const { data, isLoading, isError } = useMyTasks();
  const completeTask = useCompleteMyTask();

  const [status, setStatus] = useState<StatusFilter>("open");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [search, setSearch] = useState("");

  const allRows: TaskRow[] = useMemo(
    () => (data ?? []).map(myTaskToRow),
    [data],
  );

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRows.filter((r) => {
      if (status === "open" && r.done) return false;
      if (status === "done" && !r.done) return false;
      if (status === "overdue" && !isOverdue(r)) return false;
      if (dateFilter === "today" && !isToday(r.due)) return false;
      if (dateFilter === "week" && !withinThisWeek(r.due)) return false;
      if (q && !(r.company ?? "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allRows, status, dateFilter, search]);

  function handleComplete(row: TaskRow) {
    if (!row.done && !completeTask.isPending)
      completeTask.mutate({ leadId: row.leadId, taskId: row.id });
  }

  return (
    <div className="font-sans bg-canvas min-h-screen">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex items-center gap-2 mb-5">
          <ListChecks size={22} className="text-brand-accent" />
          <h1 className={`type-page-title ${C.color.text}`}>Задачи</h1>
        </div>

        {/* Filter bar */}
        <div className="bg-white border border-brand-border rounded-[2rem] p-4 sm:p-5 mb-4 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="type-caption text-brand-muted w-16 shrink-0">Статус</span>
            <Chip active={status === "open"} onClick={() => setStatus("open")}>
              Открытые
            </Chip>
            <Chip active={status === "done"} onClick={() => setStatus("done")}>
              Выполненные
            </Chip>
            <Chip active={status === "overdue"} onClick={() => setStatus("overdue")}>
              Просрочено
            </Chip>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="type-caption text-brand-muted w-16 shrink-0">Срок</span>
            <Chip active={dateFilter === "today"} onClick={() => setDateFilter("today")}>
              Сегодня
            </Chip>
            <Chip active={dateFilter === "week"} onClick={() => setDateFilter("week")}>
              Эта неделя
            </Chip>
            <Chip active={dateFilter === "all"} onClick={() => setDateFilter("all")}>
              Все
            </Chip>
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по клиенту…"
            className={`${C.form.field} sm:max-w-xs`}
          />
        </div>

        {/* Table */}
        <div className="bg-white border border-brand-border rounded-[2rem] p-4 sm:p-6">
          {isLoading && (
            <p className={`type-body ${C.color.mutedLight} py-6 text-center`}>
              Загрузка…
            </p>
          )}
          {!isLoading && isError && (
            <p className="type-body text-rose py-6 text-center">
              Не удалось загрузить задачи
            </p>
          )}
          {!isLoading && !isError && (
            <TaskTable
              rows={rows}
              onComplete={handleComplete}
              isCompleting={completeTask.isPending}
              emptyText="Задач нет"
            />
          )}
        </div>
      </div>
    </div>
  );
}
