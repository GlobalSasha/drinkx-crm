import type { LeadListItem } from "@/lib/types";

export type TaskUrgency = "overdue" | "today" | "upcoming" | "nodue" | "none";

type TaskFields = Pick<LeadListItem, "next_task_due_at" | "has_open_task">;

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Where the lead's nearest open task stands relative to `now`. */
export function taskUrgency(lead: TaskFields, now: Date): TaskUrgency {
  if (!lead.next_task_due_at) return lead.has_open_task ? "nodue" : "none";
  const due = new Date(lead.next_task_due_at);
  if (due.getTime() < now.getTime()) return "overdue";
  if (startOfDay(due) === startOfDay(now)) return "today";
  return "upcoming";
}

const TIME = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
const DATE = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });

/** Short Russian label for the task line under a lead in «Мои лиды». */
export function taskLabel(lead: TaskFields, now: Date): string {
  const u = taskUrgency(lead, now);
  if (u === "none") return "Нет задачи";
  if (u === "nodue") return "Задача без срока";
  const due = new Date(lead.next_task_due_at as string);
  if (u === "overdue") {
    const days = Math.floor((startOfDay(now) - startOfDay(due)) / DAY_MS);
    return days <= 0 ? `Просрочено, ${TIME.format(due)}` : `Просрочено на ${days} дн.`;
  }
  if (u === "today") return `Сегодня, ${TIME.format(due)}`;
  return `Задача ${DATE.format(due)}`;
}

const RANK: Record<TaskUrgency, number> = {
  overdue: 0,
  today: 1,
  upcoming: 2,
  nodue: 3,
  none: 4,
};

/** «Что горит» first: overdue, today, upcoming (nearest first), then
 *  tasks without a due date, then leads with no task at all. Stable. */
export function sortByUrgency<T extends TaskFields>(leads: T[], now: Date): T[] {
  return leads
    .map((lead, i) => ({ lead, i, u: taskUrgency(lead, now) }))
    .sort((a, b) => {
      if (RANK[a.u] !== RANK[b.u]) return RANK[a.u] - RANK[b.u];
      const ad = a.lead.next_task_due_at ? Date.parse(a.lead.next_task_due_at) : 0;
      const bd = b.lead.next_task_due_at ? Date.parse(b.lead.next_task_due_at) : 0;
      return ad - bd || a.i - b.i;
    })
    .map((x) => x.lead);
}

/** Number to dial from the list: primary contact first, then the lead. */
export function listCallPhone(
  lead: Pick<LeadListItem, "primary_contact_phone" | "phone">,
): string | null {
  return lead.primary_contact_phone || lead.phone || null;
}
