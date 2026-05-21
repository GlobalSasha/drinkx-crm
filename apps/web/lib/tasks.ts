// Shared task-row model + helpers used by the Today task-list widget
// and the /tasks page. A "task row" is the unified view over the data
// we currently have: DailyPlanItem rows from GET /me/today.
//
// TODO: a dedicated `GET /me/tasks` endpoint would let us aggregate
// real task-activities + followups across all of the user's leads.
// Until then the list is fed by the daily plan, and the row "type" is
// derived from DailyPlanItem.task_kind (follow_up → followup).

import type { DailyPlanItem, TimeBlock } from "@/lib/types";

export type TaskRowType = "task" | "followup";

export interface TaskRow {
  id: string;
  name: string;
  leadId: string | null;
  company: string | null;
  due: string | null; // ISO datetime, synthesised from time_block
  done: boolean;
  type: TaskRowType;
}

// DailyPlanItem only exposes a coarse `time_block`. Map each block to a
// representative hour so the table can show a clock time + detect overdue.
const TIME_BLOCK_HOUR: Record<TimeBlock, number> = {
  morning: 9,
  midday: 12,
  afternoon: 15,
  evening: 18,
};

export function synthesizeDue(
  planDate: string | undefined,
  timeBlock: TimeBlock | null,
): string | null {
  if (!planDate || !timeBlock) return null;
  const d = new Date(`${planDate}T00:00:00`);
  d.setHours(TIME_BLOCK_HOUR[timeBlock], 0, 0, 0);
  return d.toISOString();
}

export function dailyPlanItemToRow(
  item: DailyPlanItem,
  planDate: string | undefined,
): TaskRow {
  return {
    id: item.id,
    name: item.hint_one_liner || "Задача",
    leadId: item.lead_id,
    company: item.lead_company_name,
    due: synthesizeDue(planDate, item.time_block),
    done: item.done,
    type: item.task_kind === "follow_up" ? "followup" : "task",
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
  const d = new Date(due);
  return d.toDateString() === new Date().toDateString();
}
