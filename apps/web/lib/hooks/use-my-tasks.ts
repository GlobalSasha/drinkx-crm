"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
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
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, { leadId: string | null; taskId: string }>({
    mutationFn: ({ taskId }) => api.post(`/tasks/${taskId}/complete`),
    onSuccess: (_data, { leadId }) => {
      qc.invalidateQueries({ queryKey: ["my-tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
      if (leadId) {
        qc.invalidateQueries({ queryKey: ["feed", leadId] });
        qc.invalidateQueries({ queryKey: ["activities", leadId, "task"] });
      }
    },
  });
}

/** Reopen a completed task — mirror of useCompleteMyTask. */
export function useReopenMyTask() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, { leadId: string | null; taskId: string }>({
    mutationFn: ({ taskId }) => api.post(`/tasks/${taskId}/reopen`),
    onSuccess: (_data, { leadId }) => {
      qc.invalidateQueries({ queryKey: ["my-tasks"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
      if (leadId) {
        qc.invalidateQueries({ queryKey: ["feed", leadId] });
        qc.invalidateQueries({ queryKey: ["activities", leadId, "task"] });
      }
    },
  });
}
