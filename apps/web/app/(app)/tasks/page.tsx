"use client";

// /tasks — full task list: «Мои» / «Поставлено мной» / «Команда» (только
// head/admin). Опирается на GET /tasks с фильтрами по исполнителю/автору;
// бэкенд сам сужает выборку менеджеру. Статус, срок и поиск тоже уходят на
// сервер: отбор идёт в базе до счётчиков и до среза страницы.

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ListChecks, Check, ArrowUpRight, Pencil, Plus } from "lucide-react";
import { useTasks, useSetTaskDone, type TaskFilters } from "@/lib/hooks/use-tasks";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import {
  myTaskToRow,
  isOverdue,
  dueRangeFor,
  formatDueDateTime,
  type DateFilter,
  type DueRange,
  type TaskRow,
} from "@/lib/tasks";
import { apiErrorDetail } from "@/lib/api-error";
import type { MyTaskOut, TaskCounts } from "@/lib/types";
import { C } from "@/lib/design-system";
import { pageContainerVariants } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { UserSelect } from "@/components/ui/UserSelect";
import { Toast } from "@/components/ui/Toast";
import { TaskEditModal } from "@/components/tasks/TaskEditModal";
import { TaskCreateModal } from "@/components/tasks/TaskCreateModal";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/Empty";

type TabKey = "mine" | "authored" | "team";
type StatusFilter = "all" | "open" | "done" | "overdue";

/** Пауза в наборе, после которой поиск уходит на сервер. */
const SEARCH_DEBOUNCE_MS = 300;

interface ToastState {
  id: number;
  message: string;
  type: "error" | "success";
}

// Все фильтры уходят на сервер: отбор и сортировка делаются в базе до среза
// страницы. Пока страница фильтровала у себя, чипы и поиск работали только по
// тому, что поместилось в загруженные страницы.
function buildFilters(
  tab: TabKey,
  meId: string | undefined,
  assigneeFilter: string | null,
  status: StatusFilter,
  search: string,
  due: DueRange,
): TaskFilters {
  const base = {
    status,
    q: search.trim() || undefined,
    dueFrom: due.from,
    dueTo: due.to,
  };
  if (tab === "mine") return { ...base, assigneeUserId: meId };
  if (tab === "authored") return { ...base, authorUserId: meId };
  return { ...base, assigneeUserId: assigneeFilter ?? undefined };
}

/** Сколько задач на сервере под выбранным статусом. */
function countForStatus(counts: TaskCounts, status: StatusFilter): number {
  if (status === "open") return counts.open;
  if (status === "done") return counts.done;
  if (status === "overdue") return counts.overdue;
  return counts.total;
}

function emptyStateFor(tab: TabKey, hasAnyRows: boolean) {
  if (hasAnyRows) {
    return { title: "Нет задач под фильтр", description: "Смените статус или срок" };
  }
  if (tab === "authored") {
    return {
      title: "Вы ещё не ставили задач",
      description: "Нажмите «Новая задача», чтобы поставить первую",
    };
  }
  if (tab === "team") {
    return { title: "У команды нет задач", description: "Поставьте первую задачу" };
  }
  return {
    title: "Задач нет",
    description: "Когда менеджер поставит задачу — она появится в этом списке.",
  };
}

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
  showTeamDetails: boolean,
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
          <div className="flex flex-col">
            <span
              className={`type-body ${
                r.done ? "line-through text-brand-muted" : "text-brand-primary"
              }`}
            >
              {r.name}
            </span>
            {showTeamDetails && r.authorId !== r.assigneeId && r.authorName && (
              <span className="type-caption text-brand-muted">от {r.authorName}</span>
            )}
            {showTeamDetails && r.assigneeName && (
              <p className="md:hidden type-caption text-brand-muted">
                → {r.assigneeName}
              </p>
            )}
          </div>
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
    // 4. Кому
    {
      id: "assignee",
      header: "Кому",
      meta: {
        headerClassName: "hidden md:table-cell",
        cellClassName: "hidden md:table-cell",
      },
      cell: ({ row }) => (
        <span className="type-caption text-brand-muted-strong">
          {row.original.assigneeName ?? "—"}
        </span>
      ),
    },
    // 5. Срок
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
    // 6. Тип
    {
      id: "type",
      header: "Тип",
      cell: ({ row }) => <TypeBadge row={row.original} />,
    },
    // 7. Actions — edit (modal) + open-lead arrow (только если есть лид)
    {
      id: "action",
      header: "",
      meta: { width: "4.5rem", align: "right", cellClassName: "px-1 py-2.5 align-top text-right", headerClassName: "px-1" },
      cell: ({ row }) => {
        const r = row.original;
        return (
          <div className="inline-flex items-center gap-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(r);
              }}
              aria-label="Редактировать задачу"
              title="Редактировать задачу"
              className="p-1.5 rounded-full text-brand-muted hover:text-brand-primary hover:bg-brand-panel transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              <Pencil size={14} />
            </button>
            {r.leadId && (
              <ArrowUpRight
                size={15}
                className="text-brand-muted opacity-0 coarse:opacity-100 group-hover:opacity-100 transition-opacity inline-block"
              />
            )}
          </div>
        );
      },
    },
  ];
}

export default function TasksPage() {
  const router = useRouter();
  const { data: me } = useMe();
  const { data: usersData } = useUsers();
  const canSeeTeam = me?.role === "admin" || me?.role === "head";

  const [tab, setTab] = useState<TabKey>("mine");
  const [assigneeFilter, setAssigneeFilter] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusFilter>("open");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [search, setSearch] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingRow, setEditingRow] = useState<TaskRow | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastState[]>([]);

  function addToast(message: string, type: "error" | "success" = "success") {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }

  // Поиск ждёт паузы в наборе: иначе каждая буква — отдельный запрос.
  useEffect(() => {
    const timer = setTimeout(() => setSearchQuery(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search]);

  // Границы считаются один раз на выбор чипа, а не на каждый рендер: иначе
  // «сейчас» менялось бы вместе с ключом запроса и список перезагружался бы
  // сам по себе.
  const due = useMemo(() => dueRangeFor(dateFilter), [dateFilter]);

  const filters = useMemo(
    () => buildFilters(tab, me?.id, assigneeFilter, status, searchQuery, due),
    [tab, me?.id, assigneeFilter, status, searchQuery, due],
  );

  const {
    items,
    counts,
    isPending,
    isError,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useTasks(filters, { enabled: !!me });
  const setDone = useSetTaskDone();

  // Отбор целиком серверный: строки приходят уже суженными статусом, сроком
  // и поиском, доклеивать к ним нечего.
  const rows: TaskRow[] = useMemo(() => items.map(myTaskToRow), [items]);

  const isMutating = setDone.isPending;

  function handleToggle(row: TaskRow) {
    if (isMutating) return;
    setDone.mutate(
      { taskId: row.id, done: !row.done, leadId: row.leadId },
      {
        onSuccess: () => {
          if (!row.done) addToast("Задача выполнена", "success");
        },
        onError: (err) => {
          addToast(apiErrorDetail(err, "Не удалось обновить задачу"), "error");
        },
      },
    );
  }

  function handleCreated(task: MyTaskOut) {
    const assignedToMe = task.assignee_user_id === me?.id;
    let message = assignedToMe
      ? "Задача создана"
      : `Задача поставлена: ${task.assignee_name ?? "исполнителю"}`;
    if (!assignedToMe && tab === "mine") {
      message += " — смотрите во вкладке «Поставлено мной»";
    }
    addToast(message, "success");
  }

  const columns = useMemo(
    () => buildColumns(handleToggle, setEditingRow, isMutating, tab === "team"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isMutating, tab],
  );

  // «Задач нет» — только когда их нет на сервере. Раньше сюда попадала длина
  // загруженного куска, и пустая страница фильтра выглядела как пустая база.
  // counts описывают уже отфильтрованную выборку, поэтому пустой результат
  // под активным фильтром — это «ничего не найдено», а не «задач нет вовсе».
  const narrowed = status !== "all" || dateFilter !== "all" || searchQuery !== "";
  const empty = emptyStateFor(tab, (counts?.total ?? 0) > 0 || narrowed);
  const loading = isPending && items.length === 0;

  return (
    <>
      <div className={pageContainerVariants({ surface: "data" })}>
        <PageHeader
          icon={<ListChecks size={20} />}
          title="Задачи"
          actions={
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className={`${C.button.primary} type-button px-4 py-2 inline-flex items-center gap-1.5`}
            >
              <Plus size={15} />
              Новая задача
            </button>
          }
        />

        <Tabs
          value={tab}
          onValueChange={(v) => {
            setTab(v as TabKey);
            setAssigneeFilter(null);
          }}
        >
          <TabsList className="mb-4">
            <TabsTrigger value="mine">Мои</TabsTrigger>
            <TabsTrigger value="authored">Поставлено мной</TabsTrigger>
            {canSeeTeam && <TabsTrigger value="team">Команда</TabsTrigger>}
          </TabsList>
        </Tabs>

        {/* Filter bar */}
        <div className="bg-white border border-brand-border rounded-card p-4 sm:p-5 mb-4 flex flex-col gap-3">
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
            <Chip active={status === "all"} onClick={() => setStatus("all")}>
              Все
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
          {tab === "team" && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="type-caption text-brand-muted w-16 shrink-0">Исполнитель</span>
              <UserSelect
                value={assigneeFilter}
                onChange={setAssigneeFilter}
                users={usersData?.items ?? []}
                meId={me?.id}
                allowEmpty
                emptyLabel="Все"
                aria-label="Исполнитель"
                className="sm:max-w-xs"
              />
            </div>
          )}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по клиенту или задаче…"
            className={`${C.form.field} sm:max-w-xs`}
          />
        </div>

        {/* Table */}
        <div className="bg-white border border-brand-border rounded-card p-4 sm:p-6">
          {loading && (
            <p className={`type-body ${C.color.mutedLight} py-6 text-center`}>
              Загрузка…
            </p>
          )}
          {!loading && isError && (
            <p className="type-body text-rose py-6 text-center">
              Не удалось загрузить задачи
            </p>
          )}
          {!loading && !isError && (
            <DataTable
              columns={columns}
              data={rows}
              onRowClick={(row) =>
                row.leadId
                  ? router.push(`/leads/${row.leadId}?tab=tasks`)
                  : setEditingRow(row)
              }
              rowLabel={(row) =>
                row.leadId
                  ? `Открыть лид: ${row.company ?? row.name}`
                  : `Редактировать задачу: ${row.name}`
              }
              rowKey={(row) => row.id}
              emptyState={
                <Empty>
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <ListChecks />
                    </EmptyMedia>
                    <EmptyTitle>{empty.title}</EmptyTitle>
                    <EmptyDescription>{empty.description}</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              }
            />
          )}
          {!loading && !isError && hasNextPage && (
            <div className="pt-4 flex flex-col items-center gap-1">
              <button
                type="button"
                onClick={() => fetchNextPage()}
                disabled={isFetchingNextPage}
                className={`${C.button.ghost} type-body px-4 py-2 disabled:opacity-40`}
              >
                {isFetchingNextPage ? "Загрузка…" : "Показать ещё"}
              </button>
              <span className={`type-caption ${C.color.mutedLight}`}>
                показано {rows.length}
                {counts ? ` из ${countForStatus(counts, status)}` : ""}
              </span>
            </div>
          )}
        </div>
      </div>

      {editingRow && (
        <TaskEditModal
          leadId={editingRow.leadId}
          taskId={editingRow.id}
          initialTitle={editingRow.name}
          initialDueIso={editingRow.due}
          initialAssigneeId={editingRow.assigneeId}
          onClose={() => setEditingRow(null)}
        />
      )}

      <TaskCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCreated}
      />

      {/* Toast stack */}
      <div className="fixed bottom-6 right-6 flex flex-col gap-2 z-50 pointer-events-none">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} type={t.type} />
        ))}
      </div>
    </>
  );
}
