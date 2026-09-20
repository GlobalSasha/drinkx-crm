"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type { MyTaskOut, TaskCounts, TaskListOut } from "@/lib/types";

/** Сколько задач приходит в виджет «Сегодня» за один запрос. */
export const MY_TASKS_PAGE = 100;

/**
 * GET /me/tasks — задачи, которые числятся за этим человеком.
 *
 * Открытые идут первыми: до G5 сортировка начиналась со срока и обрывалась
 * на пятистах строках, поэтому пятьсот закрытых задач с более ранними датами
 * вытесняли из ответа единственную незакрытую.
 *
 * Виджет показывает одну страницу, а прогресс «N из M выполнено» берёт из
 * `counts` — они про все задачи человека, а не про загруженную страницу.
 */
export function useMyTasks() {
  const query = useQuery<TaskListOut>({
    queryKey: ["my-tasks"],
    queryFn: () => api.get<TaskListOut>(`/me/tasks?limit=${MY_TASKS_PAGE}`),
    staleTime: 15_000,
  });

  const items: MyTaskOut[] = query.data?.items ?? [];
  const counts: TaskCounts | undefined = query.data?.counts;
  const hasMore = Boolean(query.data?.next_cursor);

  return { ...query, items, counts, hasMore };
}

/** Complete a task. Задача может быть без лида, поэтому идём по id
 *  задачи, а не через lead-scoped маршрут. Инвалидирует общий список
 *  всегда, а ленту/задачи лида — только если лид есть. */
export function useCompleteMyTask() {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<unknown, ApiError, { leadId: string | null; taskId: string }>({
    mutationFn: ({ taskId }) => api.post(`/tasks/${taskId}/complete`),
    onSuccess: (_data, { leadId }) => resetTaskCache(leadId),
  });
}

/** Reopen a completed task — mirror of useCompleteMyTask. */
export function useReopenMyTask() {
  const resetTaskCache = useTaskCacheReset();
  return useMutation<unknown, ApiError, { leadId: string | null; taskId: string }>({
    mutationFn: ({ taskId }) => api.post(`/tasks/${taskId}/reopen`),
    onSuccess: (_data, { leadId }) => resetTaskCache(leadId),
  });
}
