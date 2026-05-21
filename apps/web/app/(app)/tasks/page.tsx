"use client";

// /tasks — full task database, opened from the ↗ on the Today widget.
//
// Data: fed by GET /me/today (daily plan items), same as the Today
// widget. TODO: a dedicated `GET /me/tasks` endpoint would let this
// page aggregate real task-activities + followups across all of the
// user's leads (cross-lead). Until then it mirrors the daily plan.

import { Suspense, useMemo, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { ListChecks } from "lucide-react";
import { useTodayPlan, useCompletePlanItem } from "@/lib/hooks/use-daily-plan";
import { TaskTable } from "@/components/tasks/TaskTable";
import {
  dailyPlanItemToRow,
  isOverdue,
  isToday,
  type TaskRow,
} from "@/lib/tasks";
import { C } from "@/lib/design-system";

type StatusFilter = "open" | "done" | "overdue";
type TypeFilter = "all" | "task" | "followup";
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

function withinThisWeek(due: string | null): boolean {
  if (!due) return false;
  const d = new Date(due).getTime();
  const now = Date.now();
  const weekMs = 7 * 24 * 60 * 60 * 1000;
  return d >= now - weekMs && d <= now + weekMs;
}

function TasksPageInner() {
  const searchParams = useSearchParams();
  const { data, isLoading, isError } = useTodayPlan();
  const completeItem = useCompletePlanItem();
  const planDate = data?.plan_date;

  const [status, setStatus] = useState<StatusFilter>("open");
  const [type, setType] = useState<TypeFilter>("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [search, setSearch] = useState("");

  // ?type=followup pre-applies the Follow-up filter on load (used by the
  // FOLLOW-UP counter card on Today).
  const typeParam = searchParams.get("type");
  useEffect(() => {
    if (typeParam === "followup" || typeParam === "task") setType(typeParam);
  }, [typeParam]);

  const allRows: TaskRow[] = useMemo(() => {
    const items = [...(data?.items ?? [])].sort((a, b) => a.position - b.position);
    return items.map((it) => dailyPlanItemToRow(it, planDate));
  }, [data, planDate]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRows.filter((r) => {
      // status
      if (status === "open" && r.done) return false;
      if (status === "done" && !r.done) return false;
      if (status === "overdue" && !isOverdue(r)) return false;
      // type
      if (type !== "all" && r.type !== type) return false;
      // date
      if (dateFilter === "today" && !isToday(r.due)) return false;
      if (dateFilter === "week" && !withinThisWeek(r.due)) return false;
      // search by company
      if (q && !(r.company ?? "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [allRows, status, type, dateFilter, search]);

  function handleComplete(row: TaskRow) {
    if (!row.done && !completeItem.isPending) completeItem.mutate(row.id);
  }

  return (
    <div className="font-sans bg-canvas min-h-screen">
      <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Title */}
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
            <span className="type-caption text-brand-muted w-16 shrink-0">Тип</span>
            <Chip active={type === "all"} onClick={() => setType("all")}>
              Все
            </Chip>
            <Chip active={type === "task"} onClick={() => setType("task")}>
              Задача
            </Chip>
            <Chip active={type === "followup"} onClick={() => setType("followup")}>
              Follow-up
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
              isCompleting={completeItem.isPending}
              emptyText="Задач нет"
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default function TasksPage() {
  // useSearchParams requires a Suspense boundary for static prerender.
  return (
    <Suspense fallback={null}>
      <TasksPageInner />
    </Suspense>
  );
}
