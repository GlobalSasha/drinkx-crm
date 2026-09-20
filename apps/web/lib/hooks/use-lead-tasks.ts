"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type { ActivityListOut, ActivityOut } from "@/lib/types";

// Hooks for the LeadCard «Задачи» tab. Tasks are Activity rows of
// type=task; followups have their own hooks in use-followups.ts.
// Kept separate from use-feed.ts so the tab's cache key
// (["activities", leadId, "task"]) is independent of the unified feed.

const TASKS_KEY = (leadId: string) => ["activities", leadId, "task"] as const;

/** GET /leads/{id}/activities?type=task — all task activities for a lead. */
export function useLeadTasks(leadId: string) {
  return useQuery<ActivityOut[]>({
    queryKey: TASKS_KEY(leadId),
    queryFn: async () => {
      const res = await api.get<ActivityListOut>(
        `/leads/${leadId}/activities?type=task&limit=200`,
      );
      return res.items;
    },
    enabled: !!leadId,
  });
}

export interface CreateLeadTaskIn {
  text: string;
  task_due_at?: string | null;
  /** Пусто = задачу делает владелец лида — так это работает на бэкенде. */
  assignee_user_id?: string | null;
}

/** POST /leads/{id}/activities (type=task). Mirrors FeedComposer's
 *  payload so a task created here renders identically in the feed. */
export function useCreateLeadTask(leadId: string) {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<ActivityOut, ApiError, CreateLeadTaskIn>({
    mutationFn: ({ text, task_due_at, assignee_user_id }) =>
      api.post<ActivityOut>(`/leads/${leadId}/activities`, {
        type: "task",
        body: text,
        task_due_at: task_due_at ?? null,
        assignee_user_id: assignee_user_id ?? null,
        payload_json: { title: text, source: "tasks_tab" },
      }),
    onSuccess: () => resetTaskCache(leadId),
  });
}

/** POST /leads/{id}/activities/{id}/complete-task — reuses the same
 *  endpoint as the feed, but invalidates the tasks-tab cache too. */
export function useCompleteLeadTask(leadId: string) {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<ActivityOut>(
        `/leads/${leadId}/activities/${activityId}/complete-task`,
      ),
    onSuccess: () => resetTaskCache(leadId),
  });
}

/** POST /leads/{id}/activities/{id}/reopen-task — bring a completed task
 *  back to the active list. Mirrors the complete hook's invalidations. */
export function useReopenLeadTask(leadId: string) {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<ActivityOut>(
        `/leads/${leadId}/activities/${activityId}/reopen-task`,
      ),
    onSuccess: () => resetTaskCache(leadId),
  });
}

/** DELETE /leads/{id}/activities/{activityId} — archive a task (soft-delete).
 *  The backend sets archived_at and returns the updated row. */
export function useArchiveLeadTask(leadId: string) {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.delete<ActivityOut>(`/leads/${leadId}/activities/${activityId}`),
    onSuccess: () => resetTaskCache(leadId),
  });
}

/** POST /leads/{id}/activities/{activityId}/restore — restore an archived task. */
export function useRestoreLeadTask(leadId: string) {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<ActivityOut>(`/leads/${leadId}/activities/${activityId}/restore`),
    onSuccess: () => resetTaskCache(leadId),
  });
}

/** GET /leads/{id}/archive — list archived activities for a lead. */
export function useLeadArchive(leadId: string) {
  return useQuery<{ items: ActivityOut[] }>({
    queryKey: ["lead-archive", leadId],
    queryFn: () =>
      api.get<{ items: ActivityOut[] }>(`/leads/${leadId}/activities/archive`),
    enabled: !!leadId,
  });
}
