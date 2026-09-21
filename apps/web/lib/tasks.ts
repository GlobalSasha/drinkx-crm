// Shared task-row model + helpers for the Today task-list widget and
// the /tasks page.
//
// Tasks are MANAGER-ENTERED ONLY — no AI anywhere. The data source is
// GET /me/tasks (задачи, которые числятся за человеком) или GET /tasks
// (список с фильтрами для руководителя), NOT the AI daily plan.
// Due dates are the manager's own values.

import type { MyTaskOut } from "@/lib/types";

export interface TaskRow {
  id: string;
  /** Пусто у задач без лида. */
  leadId: string | null;
  name: string;
  company: string | null;
  due: string | null; // real task_due_at, manager-set
  done: boolean;
  /** Уже разрешённый исполнитель: явный, иначе владелец лида, иначе автор. */
  assigneeId: string | null;
  assigneeName: string | null;
  /**
   * Исполнитель, записанный в самой задаче. Пусто = «по умолчанию»
   * (владелец лида, иначе автор). Форма правки работает именно с ним:
   * подставишь туда вычисленного — первое же сохранение превратит
   * неявное назначение в явное.
   */
  explicitAssigneeId: string | null;
  authorId: string | null;
  authorName: string | null;
}

export function myTaskToRow(t: MyTaskOut): TaskRow {
  return {
    id: t.id,
    leadId: t.lead_id,
    name: t.text,
    company: t.lead_company_name,
    due: t.task_due_at,
    done: t.task_done,
    assigneeId: t.assignee_user_id,
    assigneeName: t.assignee_name,
    explicitAssigneeId: t.explicit_assignee_user_id,
    authorId: t.author_user_id,
    authorName: t.author_name,
  };
}

export function isOverdue(row: Pick<TaskRow, "due" | "done">): boolean {
  if (!row.due || row.done) return false;
  return new Date(row.due).getTime() < Date.now();
}

export function formatDueDateTime(due: string | null): string {
  if (!due) return "—";
  const d = new Date(due);
  if (Number.isNaN(d.getTime())) return "—";
  const date = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  const time = d.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${date} · ${time}`;
}

export function isToday(due: string | null): boolean {
  if (!due) return false;
  return new Date(due).toDateString() === new Date().toDateString();
}

/** Границы чипа «Срок» на странице «Задачи». */
export interface DueRange {
  from?: string;
  to?: string;
}

export type DateFilter = "today" | "week" | "all";

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

/**
 * ISO-границы для `due_from` / `due_to` у GET /tasks — полуоткрытый интервал
 * `[from, to)`.
 *
 * Календарь считает клиент, в своём часовом поясе: сервер границы только
 * сравнивает и про пояс рабочего пространства ничего не знает
 * (docs/TASK_LISTS.md §6). «Эта неделя» — прежнее окно вокруг текущего
 * момента, а не календарная неделя; семантику чипа правка не меняет.
 */
export function dueRangeFor(filter: DateFilter, now: Date = new Date()): DueRange {
  if (filter === "today") {
    const from = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const to = new Date(from);
    to.setDate(to.getDate() + 1);
    return { from: from.toISOString(), to: to.toISOString() };
  }
  if (filter === "week") {
    return {
      from: new Date(now.getTime() - WEEK_MS).toISOString(),
      to: new Date(now.getTime() + WEEK_MS).toISOString(),
    };
  }
  return {};
}
