// Client-side task-reminder logic. Manager-entered tasks with a
// task_due_at fire an in-app glass toast when their time arrives, while
// the CRM tab is open. State (dismissed / snoozed) lives in localStorage
// keyed by user id so it survives reloads and doesn't leak across
// accounts on a shared browser.
//
// The selection logic is a pure function so it can be reasoned about and
// tested without the DOM.

import type { MyTaskOut } from "@/lib/types";

type NumMap = Record<string, number>;

const ackKey = (userId: string) => `drinkx.reminders.ack.${userId}`;
const snoozeKey = (userId: string) => `drinkx.reminders.snooze.${userId}`;

function readMap(key: string): NumMap {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? (parsed as NumMap) : {};
  } catch {
    return {};
  }
}

function writeMap(key: string, map: NumMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(map));
  } catch {
    /* quota exceeded / storage disabled — reminders just won't persist */
  }
}

export function loadAcks(userId: string): NumMap {
  return readMap(ackKey(userId));
}

export function loadSnoozes(userId: string): NumMap {
  return readMap(snoozeKey(userId));
}

/** Mark a task's reminder dismissed for THIS due time. Keyed by the due
 *  timestamp so that re-scheduling the task (new due) re-fires it. */
export function ackReminder(userId: string, taskId: string, dueMs: number): void {
  const m = readMap(ackKey(userId));
  m[taskId] = dueMs;
  writeMap(ackKey(userId), m);
}

/** Snooze a task's reminder until `untilMs`. */
export function snoozeReminder(userId: string, taskId: string, untilMs: number): void {
  const m = readMap(snoozeKey(userId));
  m[taskId] = untilMs;
  writeMap(snoozeKey(userId), m);
}

/** Local midnight of the day containing `now` — the catch-up cutoff so
 *  reminders that came due earlier today still fire on next open, but
 *  ancient overdue tasks don't suddenly pop. */
export function startOfToday(now: number): number {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

/** Tasks whose reminder should be showing right now. Pure. */
export function selectDueReminders(
  tasks: MyTaskOut[],
  now: number,
  acks: NumMap,
  snoozes: NumMap,
  cutoffMs: number,
): MyTaskOut[] {
  const out: MyTaskOut[] = [];
  for (const t of tasks) {
    if (t.task_done || !t.task_due_at) continue;
    const dueMs = Date.parse(t.task_due_at);
    if (Number.isNaN(dueMs)) continue;
    if (dueMs > now) continue; // not due yet
    if (dueMs < cutoffMs) continue; // older than the catch-up cutoff
    if (acks[t.id] === dueMs) continue; // dismissed for this due time
    const snoozedUntil = snoozes[t.id];
    if (snoozedUntil && snoozedUntil > now) continue; // still snoozed
    out.push(t);
  }
  out.sort(
    (a, b) => Date.parse(a.task_due_at as string) - Date.parse(b.task_due_at as string),
  );
  return out;
}
