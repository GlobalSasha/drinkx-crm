"use client";

import { useMemo, useState } from "react";
import { CheckSquare, Square, Plus, Calendar, X, Loader2, Paperclip, Search, ChevronDown, Pencil, ListChecks, Trash2, UserRound } from "lucide-react";
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
import { UserSelect } from "@/components/ui/UserSelect";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import { useUpdateTask } from "@/lib/hooks/use-tasks";
import { apiErrorDetail } from "@/lib/api-error";
import { C } from "@/lib/design-system";
import type { MyTaskOut } from "@/lib/types";

interface Props {
  leadId: string;
}

function taskTitle(a: MyTaskOut): string {
  return a.text || "Задача";
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
  const {
    items: tasks,
    counts,
    isLoading,
    isError,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useLeadTasks(leadId);
  const createTask = useCreateLeadTask(leadId);
  const completeTask = useCompleteLeadTask(leadId);
  const reopenTask = useReopenLeadTask(leadId);
  const archiveTask = useArchiveLeadTask(leadId);

  const { data: me } = useMe();
  const { data: usersData } = useUsers();
  const users = usersData?.items ?? [];
  // Поручить задачу другому человеку может только руководитель или админ —
  // тот же порядок, что на бэкенде.
  const canAssign = me?.role === "admin" || me?.role === "head";

  const update = useUpdateTask();
  const [delegatingId, setDelegatingId] = useState<string | null>(null);
  // Что человек выбрал, пока запрос в пути. На ошибке селектор остаётся
  // открытым с этим значением — раньше он закрывался сразу после mutate, и
  // при отказе выбор пропадал вместе с объяснением.
  const [pendingAssignee, setPendingAssignee] = useState<string | null>(null);

  const handleDelegate = (taskId: string, v: string | null) => {
    // Пусто — снять явного исполнителя, задачу делает владелец лида.
    setPendingAssignee(v);
    update.mutate(
      { taskId, body: { assignee_user_id: v }, leadId },
      {
        onSuccess: () => {
          setDelegatingId(null);
          setPendingAssignee(null);
        },
      },
    );
  };

  const [adding, setAdding] = useState(false);
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [due, setDue] = useState(""); // datetime-local: yyyy-mm-ddTHH:mm
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [editingTask, setEditingTask] = useState<MyTaskOut | null>(null);

  // Отметка «сделано», переоткрытие и архивация раньше молча ничего не
  // делали при ошибке: у строки нет своего места под сообщение, поэтому
  // показываем его над списком.
  const rowActionError = completeTask.isError
    ? apiErrorDetail(completeTask.error, "Не удалось закрыть задачу")
    : reopenTask.isError
      ? apiErrorDetail(reopenTask.error, "Не удалось вернуть задачу в работу")
      : archiveTask.isError
        ? apiErrorDetail(archiveTask.error, "Не удалось архивировать задачу")
        : null;

  function assigneeName(id: string): string {
    if (id === me?.id) return "вам";
    const u = users.find((x) => x.id === id);
    return u?.name || u?.email || id.slice(0, 8);
  }

  // Порядок задаёт база: не сделано → срок (пустые в конец) → id. Раньше
  // список пересортировывался здесь, и это работало ровно до тех пор, пока
  // всё помещалось в один ответ. Поиск по-прежнему клиентский — он сужает
  // загруженные страницы, о чём под списком написано прямо.
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return tasks;
    return tasks.filter((a) => taskTitle(a).toLowerCase().includes(q));
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
      {
        text: t,
        task_due_at: iso,
        assignee_user_id: canAssign ? assigneeId : undefined,
      },
      {
        onSuccess: () => {
          setText("");
          setDue("");
          setAssigneeId(null);
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
          {canAssign && (
            <UserSelect
              value={assigneeId}
              onChange={setAssigneeId}
              users={users}
              meId={me?.id}
              allowEmpty
              emptyLabel="Владелец лида"
              disabled={createTask.isPending}
              aria-label="Исполнитель задачи"
              className="sm:w-56"
            />
          )}
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
          {createTask.isError && (
            <p role="alert" className="text-xs text-rose">
              {apiErrorDetail(createTask.error, "Не удалось сохранить задачу")}
            </p>
          )}
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

      {rowActionError && (
        <p role="alert" className="type-caption text-rose pb-2">
          {rowActionError}
        </p>
      )}

      {!isLoading && !isError && rows.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><ListChecks /></EmptyMedia>
            <EmptyTitle>
              {/* «Задач пока нет» — только когда их нет на сервере, а не когда
                  поиск или незагруженные страницы скрыли всё найденное. */}
              {(counts?.total ?? 0) > 0 ? "Ничего не найдено" : "Задач пока нет"}
            </EmptyTitle>
            <EmptyDescription>
              {(counts?.total ?? 0) > 0
                ? "Попробуйте другой запрос, очистите поиск или загрузите ещё задачи."
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
                    {a.explicit_assignee_user_id && (
                      <span className="inline-flex items-center gap-1 type-caption text-brand-muted mt-0.5">
                        <UserRound size={11} /> поручено:{" "}
                        {assigneeName(a.explicit_assignee_user_id)}
                      </span>
                    )}
                    {delegatingId === a.id && (
                      <div className="mt-2 max-w-xs">
                        <UserSelect
                          value={
                            update.isError || update.isPending
                              ? pendingAssignee
                              : a.explicit_assignee_user_id
                          }
                          onChange={(v) => handleDelegate(a.id, v)}
                          users={users}
                          meId={me?.id}
                          allowEmpty
                          emptyLabel="Владелец лида"
                          disabled={update.isPending}
                          aria-label="Кому поручить задачу"
                        />
                        {update.isError && (
                          <p role="alert" className="mt-1 type-caption text-brand-danger">
                            {apiErrorDetail(update.error, "Не удалось поручить задачу")}
                          </p>
                        )}
                      </div>
                    )}
                  </ItemContent>
                  <ItemActions>
                    {canAssign && (
                      <button
                        type="button"
                        onClick={() => setDelegatingId(delegatingId === a.id ? null : a.id)}
                        aria-expanded={delegatingId === a.id}
                        title="Поручить задачу сотруднику"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full type-caption font-semibold bg-white border border-brand-border text-brand-muted hover:text-brand-primary hover:border-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-1"
                      >
                        <UserRound size={13} />
                        <span className="hidden sm:inline">Поручить</span>
                      </button>
                    )}
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

      {/* История не тянется сама: первая страница — то, что нужно сейчас.
          Счётчик берётся с сервера, поэтому он про все задачи лида, а не
          про загруженные. */}
      {!isLoading && !isError && hasNextPage && (
        <div className="pt-3 flex flex-col items-center gap-1">
          <Button
            variant="pill"
            size="sm"
            type="button"
            onClick={() => fetchNextPage()}
            disabled={isFetchingNextPage}
          >
            {isFetchingNextPage ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              "Показать ещё"
            )}
          </Button>
          {counts && (
            <span className="type-caption text-brand-muted">
              показано {tasks.length} из {counts.total}
              {search.trim() ? " — поиск идёт по загруженным" : ""}
            </span>
          )}
        </div>
      )}

      {editingTask && (
        <TaskEditModal
          leadId={leadId}
          taskId={editingTask.id}
          initialTitle={taskTitle(editingTask)}
          initialDueIso={editingTask.task_due_at}
          initialAssigneeId={editingTask.explicit_assignee_user_id}
          onClose={() => setEditingTask(null)}
        />
      )}
    </Card>
  );
}
