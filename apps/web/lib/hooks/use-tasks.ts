"use client";

// Задачи вне контекста лида — страница «Задачи» и постановка задач команде.
//
// GET /tasks отдаёт список с фильтрами: руководитель видит всю команду,
// менеджеру бэкенд принудительно сужает выборку до своих задач. Правка,
// закрытие и переоткрытие идут по id задачи, а не через маршрут лида —
// у задачи лида может не быть вовсе.

import {
  keepPreviousData,
  useMutation,
  useQuery,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type {
  MyTaskOut,
  TaskCreateIn,
  TaskPatchIn,
  TaskStatusFilter,
} from "@/lib/types";

export interface TaskFilters {
  assigneeUserId?: string;
  authorUserId?: string;
  status?: TaskStatusFilter;
}

function toQuery(filters: TaskFilters): string {
  const params = new URLSearchParams();
  if (filters.assigneeUserId) params.set("assignee_user_id", filters.assigneeUserId);
  if (filters.authorUserId) params.set("author_user_id", filters.authorUserId);
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useTasks(
  filters: TaskFilters = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery<MyTaskOut[]>({
    queryKey: ["tasks", filters],
    queryFn: () => api.get<MyTaskOut[]>(`/tasks${toQuery(filters)}`),
    staleTime: 15_000,
    // Смена вкладки = новый ключ; без этого таблица мигает «Загрузка…».
    placeholderData: keepPreviousData,
    // Пока /me не ответил, «Мои» у руководителя показали бы всю команду.
    enabled: options.enabled ?? true,
  });
}

export function useCreateTask() {
  const reset = useTaskCacheReset();
  return useMutation<MyTaskOut, ApiError, TaskCreateIn>({
    mutationFn: (body) => api.post<MyTaskOut>("/tasks", body),
    onSuccess: (task) => reset(task.lead_id),
  });
}

export function useUpdateTask() {
  const reset = useTaskCacheReset();
  return useMutation<
    MyTaskOut,
    ApiError,
    { taskId: string; body: TaskPatchIn; leadId?: string | null }
  >({
    mutationFn: ({ taskId, body }) => api.patch<MyTaskOut>(`/tasks/${taskId}`, body),
    onSuccess: (_task, { leadId }) => reset(leadId),
  });
}

/** Закрыть или переоткрыть задачу по её id — работает и без лида. */
export function useSetTaskDone() {
  const reset = useTaskCacheReset();
  return useMutation<
    MyTaskOut,
    ApiError,
    { taskId: string; done: boolean; leadId?: string | null }
  >({
    mutationFn: ({ taskId, done }) =>
      api.post<MyTaskOut>(`/tasks/${taskId}/${done ? "complete" : "reopen"}`),
    onSuccess: (_task, { leadId }) => reset(leadId),
  });
}
