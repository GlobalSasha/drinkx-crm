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

/** Complete a task. The endpoint is lead-scoped, so we need the
 *  lead id alongside the activity id. Invalidates the cross-lead list
 *  plus that lead's feed/tasks caches. */
export function useCompleteMyTask() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, { leadId: string; taskId: string }>({
    mutationFn: ({ leadId, taskId }) =>
      api.post(`/leads/${leadId}/activities/${taskId}/complete-task`),
    onSuccess: (_data, { leadId }) => {
      qc.invalidateQueries({ queryKey: ["my-tasks"] });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["activities", leadId, "task"] });
    },
  });
}
