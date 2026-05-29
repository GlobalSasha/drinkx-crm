"use client";

// /tasks — full task list, opened from the ↗ on the Today widget.
//
// Manager-entered tasks only (no AI). Fed by GET /me/tasks — all
// Activity(type=task) across the user's leads, with their own due dates.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ListChecks, Check, ArrowUpRight, Pencil } from "lucide-react";
import {
  useMyTasks,
  useCompleteMyTask,
  useReopenMyTask,
} from "@/lib/hooks/use-my-tasks";
import {
  myTaskToRow,
  isOverdue,
  isToday,
  withinThisWeek,
  formatDueDateTime,
  type TaskRow,
} from "@/lib/tasks";
import { C } from "@/lib/design-system";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { TaskEditModal } from "@/components/tasks/TaskEditModal";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/Empty";

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

function TypeBadge({ row }: { row: TaskRow }) {
  if (isOverdue(row)) {
    return <Badge variant="rose">просрочено</Badge>;
  }
  return <Badge variant="success">задача</Badge>;
}

function buildColumns(
  onToggle: (row: TaskRow) => void,
  onEdit: (row: TaskRow) => void,
  isMutating: boolean,
): ColumnDef<TaskRow, unknown>[] {
  return [
    // 1. Checkbox — toggles complete / reopen
    {
      id: "checkbox",
      header: "",
      meta: { width: "2.25rem", cellClassName: "px-1 py-2.5", headerClassName: "px-1" },
      cell: ({ row }) => {
        const r = row.original;
        return (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (!isMutating) onToggle(r);
            }}
            disabled={isMutating}
            aria-label={r.done ? "Вернуть в активные" : "Отметить выполненной"}
            title={r.done ? "Вернуть в активные" : "Отметить выполненной"}
            className={`shrink-0 w-5 h-5 rounded-full border-[1.5px] flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1 ${
              r.done
                ? "border-success bg-success hover:bg-success/80"
                : "border-brand-border hover:border-brand-accent hover:bg-brand-soft/40"
            } disabled:opacity-60`}
          >
            {r.done && <Check size={12} className="text-white" />}
          </button>
        );
      },
    },
    // 2. Задача
    {
      id: "name",
      header: "Задача",
      cell: ({ row }) => {
        const r = row.original;
        return (
          <span
            className={`type-body ${
              r.done ? "line-through text-brand-muted" : "text-brand-primary"
            }`}
          >
            {r.name}
          </span>
        );
      },
    },
    // 3. Клиент
    {
      id: "company",
      header: "Клиент",
      cell: ({ row }) => (
        <span className="type-caption text-brand-muted-strong">
          {row.original.company ?? "—"}
        </span>
      ),
    },
    // 4. Срок
    {
      id: "due",
      header: "Срок",
      meta: { cellClassName: "px-2 py-2.5 align-top whitespace-nowrap" },
      cell: ({ row }) => {
        const r = row.original;
        const overdue = isOverdue(r);
        return (
          <span
            className={`type-caption ${
              overdue ? "text-rose font-semibold" : "text-brand-muted"
            }`}
          >
            {formatDueDateTime(r.due)}
            {overdue && " · просрочено"}
          </span>
        );
      },
    },
    // 5. Тип
    {
      id: "type",
      header: "Тип",
      cell: ({ row }) => <TypeBadge row={row.original} />,
    },
    // 6. Actions — edit (modal) + open-lead arrow
    {
      id: "action",
      header: "",
      meta: { width: "4.5rem", align: "right", cellClassName: "px-1 py-2.5 align-top text-right", headerClassName: "px-1" },
      cell: ({ row }) => (
        <div className="inline-flex items-center gap-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit(row.original);
            }}
            aria-label="Редактировать задачу"
            title="Редактировать задачу"
            className="p-1.5 rounded-full text-brand-muted hover:text-brand-primary hover:bg-brand-panel transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <Pencil size={14} />
          </button>
          <ArrowUpRight
            size={15}
            className="text-brand-muted opacity-0 group-hover:opacity-100 transition-opacity inline-block"
          />
        </div>
      ),
    },
  ];
}

export default function TasksPage() {
  const router = useRouter();
  const { data, isLoading, isError } = useMyTasks();
  const completeTask = useCompleteMyTask();
  const reopenTask = useReopenMyTask();

  const [status, setStatus] = useState<StatusFilter>("open");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [search, setSearch] = useState("");
  const [editingRow, setEditingRow] = useState<TaskRow | null>(null);

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

  const isMutating = completeTask.isPending || reopenTask.isPending;

  function handleToggle(row: TaskRow) {
    if (isMutating) return;
    if (row.done) reopenTask.mutate({ leadId: row.leadId, taskId: row.id });
    else completeTask.mutate({ leadId: row.leadId, taskId: row.id });
  }

  const columns = useMemo(
    () => buildColumns(handleToggle, setEditingRow, isMutating),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isMutating],
  );

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
            <DataTable
              columns={columns}
              data={rows}
              onRowClick={(row) =>
                router.push(`/leads/${row.leadId}?tab=tasks`)
              }
              rowLabel={(row) => `Открыть лид: ${row.company ?? row.name}`}
              rowKey={(row) => row.id}
              emptyState={
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <ListChecks />
                    </EmptyMedia>
                    <EmptyTitle>Задач нет</EmptyTitle>
                    <EmptyDescription>
                      Когда менеджер поставит задачу — она появится в этом списке.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              }
            />
          )}
        </div>
      </div>

      {editingRow && (
        <TaskEditModal
          leadId={editingRow.leadId}
          taskId={editingRow.id}
          initialTitle={editingRow.name}
          initialDueIso={editingRow.due}
          onClose={() => setEditingRow(null)}
        />
      )}
    </div>
  );
}
