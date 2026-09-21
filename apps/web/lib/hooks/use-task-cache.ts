"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";

// One place that knows which caches show a task.
//
// There were three sets of invalidations and they had drifted apart: the
// lead-card hooks never touched ["tasks"], so closing a task on the card left
// the «Задачи» page showing it as open until something else refetched, and
// completing one there did not refresh ["my-tasks"] either (BUG-07).
//
// A task appears in five places, and a mutation anywhere has to be visible in
// all of them:
//
//   ["tasks", filters]              the Задачи page
//   ["my-tasks"]                    the current user's own list
//   ["daily-plan", "today"]         the Сегодня screen
//   ["feed", leadId]                the lead's activity feed
//   ["activities", leadId, "task"]  the lead card's Задачи tab
//   ["lead-archive", leadId]        the lead's archive, for archive/restore
//
// Lead-scoped keys are only invalidated when the task belongs to a lead;
// standalone tasks have none.

/** Invalidate every cache that can be showing this task. */
export function invalidateTaskQueries(
  qc: QueryClient,
  leadId?: string | null,
): void {
  qc.invalidateQueries({ queryKey: ["tasks"] });
  qc.invalidateQueries({ queryKey: ["my-tasks"] });
  qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
  if (leadId) {
    qc.invalidateQueries({ queryKey: ["feed", leadId] });
    qc.invalidateQueries({ queryKey: ["activities", leadId, "task"] });
    qc.invalidateQueries({ queryKey: ["lead-archive", leadId] });
  }
}

/** Hook form: `const resetTaskCache = useTaskCacheReset()`. */
export function useTaskCacheReset() {
  const qc = useQueryClient();
  return (leadId?: string | null) => invalidateTaskQueries(qc, leadId);
}
