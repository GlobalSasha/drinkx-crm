"use client";

// Задачи вне контекста лида — страница «Задачи» и постановка задач команде.
//
// GET /tasks отдаёт список с фильтрами: руководитель видит всю команду,
// менеджеру бэкенд принудительно сужает выборку до своих задач. Правка,
// закрытие и переоткрытие идут по id задачи, а не через маршрут лида —
// у задачи лида может не быть вовсе.

import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { useTaskCacheReset } from "@/lib/hooks/use-task-cache";
import type {
  MyTaskOut,
  TaskCounts,
  TaskCreateIn,
  TaskListOut,
  TaskPatchIn,
  TaskStatusFilter,
} from "@/lib/types";

export interface TaskFilters {
  assigneeUserId?: string;
  authorUserId?: string;
  status?: TaskStatusFilter;
}

/** Размер страницы списка задач. Дальше — «Показать ещё». */
export const TASKS_PAGE = 50;

function toQuery(filters: TaskFilters, cursor: string | null): string {
  const params = new URLSearchParams({ limit: String(TASKS_PAGE) });
  if (filters.assigneeUserId) params.set("assignee_user_id", filters.assigneeUserId);
  if (filters.authorUserId) params.set("author_user_id", filters.authorUserId);
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (cursor) params.set("cursor", cursor);
  return `?${params.toString()}`;
}

/**
 * GET /tasks — постранично, курсором.
 *
 * `status` уходит на сервер: отбор «открытые / закрытые / просроченные» и
 * сортировка делаются в базе до среза страницы. Раньше страница брала одним
 * запросом до 500 строк и фильтровала их у себя — при большем числе задач
 * нужная просто не приезжала.
 *
 * `counts` описывают всю серверную выборку, поэтому чипы и пустые состояния
 * говорят о задачах, а не о том, сколько страниц успели загрузить.
 */
export function useTasks(
  filters: TaskFilters = {},
  options: { enabled?: boolean } = {},
) {
  const query = useInfiniteQuery<TaskListOut>({
    queryKey: ["tasks", filters],
    queryFn: ({ pageParam }) =>
      api.get<TaskListOut>(`/tasks${toQuery(filters, (pageParam as string) ?? null)}`),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 15_000,
    // Смена вкладки = новый ключ; без этого таблица мигает «Загрузка…».
    placeholderData: keepPreviousData,
    // Пока /me не ответил, «Мои» у руководителя показали бы всю команду.
    enabled: options.enabled ?? true,
  });

  const pages = query.data?.pages ?? [];
  const items: MyTaskOut[] = pages.flatMap((p) => p.items);
  const counts: TaskCounts | undefined = pages.at(-1)?.counts;

  return { ...query, items, counts };
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
