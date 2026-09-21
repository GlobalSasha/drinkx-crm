"use client";

import { useQuery, useMutation, useInfiniteQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type { ActivityOut, MyTaskOut, TaskCounts, TaskListOut } from "@/lib/types";

// Hooks for the LeadCard «Задачи» tab. Tasks are Activity rows of
// type=task; followups have their own hooks in use-followups.ts.
// Kept separate from use-feed.ts so the tab's cache key
// (["activities", leadId, "task"]) is independent of the unified feed.

const TASKS_KEY = (leadId: string) => ["activities", leadId, "task"] as const;

/** Сколько задач лида приходит за один запрос. Дальше — «Показать ещё». */
export const LEAD_TASKS_PAGE = 50;

/**
 * GET /leads/{id}/tasks — задачи лида, открытые первыми.
 *
 * Раньше тут был `?type=task&limit=200` к ленте активностей, и курсор из
 * ответа выбрасывался. На лиде с историей длиннее двухсот записей открытая
 * задача, заведённая раньше остальных, в карточку не попадала вообще (G5,
 * дефект A). Теперь порядок задаёт база (не сделано → срок → id), а страницы
 * подтягиваются по курсору.
 *
 * Вся история автоматически не грузится: первая страница — то, что нужно
 * сейчас, остальное по кнопке.
 */
export function useLeadTasks(leadId: string) {
  const query = useInfiniteQuery<TaskListOut>({
    queryKey: TASKS_KEY(leadId),
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(LEAD_TASKS_PAGE) });
      if (pageParam) params.set("cursor", String(pageParam));
      return api.get<TaskListOut>(`/leads/${leadId}/tasks?${params.toString()}`);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!leadId,
  });

  const pages = query.data?.pages ?? [];
  const items: MyTaskOut[] = pages.flatMap((p) => p.items);
  // Счётчики берём из последнего ответа: они описывают всю выборку на
  // сервере, а не то, что успели загрузить.
  const counts: TaskCounts | undefined = pages.at(-1)?.counts;

  return { ...query, items, counts };
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
