// Shared task-row model + helpers for the Today task-list widget and
// the /tasks page.
//
// Tasks are MANAGER-ENTERED ONLY — no AI anywhere. The data source is
// GET /me/tasks (manual Activity(type=task) across the user's leads),
// NOT the AI daily plan. Due dates are the manager's own values.

import type { MyTaskOut } from "@/lib/types";

export interface TaskRow {
  id: string;
  leadId: string;
  name: string;
  company: string | null;
  due: string | null; // real task_due_at, manager-set
  done: boolean;
}

export function myTaskToRow(t: MyTaskOut): TaskRow {
  return {
    id: t.id,
    leadId: t.lead_id,
    name: t.text,
    company: t.lead_company_name,
    due: t.task_due_at,
    done: t.task_done,
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

export function withinThisWeek(due: string | null): boolean {
  if (!due) return false;
  const d = new Date(due).getTime();
  const now = Date.now();
  const weekMs = 7 * 24 * 60 * 60 * 1000;
  return d >= now - weekMs && d <= now + weekMs;
}
