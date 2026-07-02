"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMyTasks } from "@/lib/hooks/use-my-tasks";
import { useMe } from "@/lib/hooks/use-me";
import {
  loadAcks,
  loadSnoozes,
  ackReminder,
  snoozeReminder,
  selectDueReminders,
  startOfToday,
} from "@/lib/reminders";
import type { MyTaskOut } from "@/lib/types";
import { ReminderToast } from "./ReminderToast";

const TICK_MS = 30_000;
const SNOOZE_MS = 10 * 60_000;
const MAX_VISIBLE = 5;

// Global, always-mounted reminder engine. Re-evaluates the manager's
// tasks every TICK_MS against the wall clock and pops a glass toast for
// each task whose due time has arrived (and isn't dismissed/snoozed).
export function TaskReminders() {
  const router = useRouter();
  const me = useMe().data;
  const userId = me?.id ?? null;
  const { data: tasks } = useMyTasks();

  const [now, setNow] = useState(() => Date.now());
  const [acks, setAcks] = useState<Record<string, number>>({});
  const [snoozes, setSnoozes] = useState<Record<string, number>>({});

  // (Re)load persisted state when the user resolves or changes.
  useEffect(() => {
    if (!userId) return;
    setAcks(loadAcks(userId));
    setSnoozes(loadSnoozes(userId));
  }, [userId]);

  // Advance the clock so due times fire without needing a data refetch.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  if (!userId || !tasks) return null;

  const due = selectDueReminders(tasks, now, acks, snoozes, startOfToday(now)).slice(
    0,
    MAX_VISIBLE,
  );
  if (due.length === 0) return null;

  function handleClose(task: MyTaskOut) {
    if (!userId || !task.task_due_at) return;
    const dueMs = Date.parse(task.task_due_at);
    ackReminder(userId, task.id, dueMs);
    setAcks((m) => ({ ...m, [task.id]: dueMs }));
  }

  function handleSnooze(task: MyTaskOut) {
    if (!userId) return;
    const until = Date.now() + SNOOZE_MS;
    snoozeReminder(userId, task.id, until);
    setSnoozes((m) => ({ ...m, [task.id]: until }));
  }

  function handleOpen(task: MyTaskOut) {
    handleClose(task);
    router.push(`/leads/${task.lead_id}?tab=tasks`);
  }

  return (
    <div
      className="fixed right-4 sm:right-6 z-40 flex flex-col gap-3 max-w-[calc(100vw-2rem)] pointer-events-none"
      style={{ bottom: "max(1rem, env(safe-area-inset-bottom))" }}
    >
      {due.map((t) => (
        <ReminderToast
          key={t.id}
          task={t}
          onOpen={() => handleOpen(t)}
          onSnooze={() => handleSnooze(t)}
          onClose={() => handleClose(t)}
        />
      ))}
    </div>
  );
}
