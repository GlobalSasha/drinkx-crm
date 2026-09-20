"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type { MyTaskOut } from "@/lib/types";

// Cross-lead list of the manager's own tasks (no AI). Fed by
// GET /me/tasks. Used by the Today widget and the /tasks page.
export function useMyTasks() {
  return useQuery<MyTaskOut[]>({
    queryKey: ["my-tasks"],
    queryFn: () => api.get<MyTaskOut[]>("/me/tasks"),
    staleTime: 15_000,
  });
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
