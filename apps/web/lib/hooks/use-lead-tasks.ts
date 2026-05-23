"use client";

import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
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
}

/** POST /leads/{id}/activities (type=task). Mirrors FeedComposer's
 *  payload so a task created here renders identically in the feed. */
export function useCreateLeadTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ActivityOut, ApiError, CreateLeadTaskIn>({
    mutationFn: ({ text, task_due_at }) =>
      api.post<ActivityOut>(`/leads/${leadId}/activities`, {
        type: "task",
        body: text,
        task_due_at: task_due_at ?? null,
        payload_json: { title: text, source: "tasks_tab" },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(leadId) });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}

/** POST /leads/{id}/activities/{id}/complete-task — reuses the same
 *  endpoint as the feed, but invalidates the tasks-tab cache too. */
export function useCompleteLeadTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<ActivityOut>(
        `/leads/${leadId}/activities/${activityId}/complete-task`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(leadId) });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}

export interface UpdateLeadTaskIn {
  activityId: string;
  body?: string;
  task_due_at?: string | null;
}

/** PATCH /leads/{id}/activities/{activityId} — update task title and/or due date. */
export function useUpdateLeadTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ActivityOut, ApiError, UpdateLeadTaskIn>({
    mutationFn: ({ activityId, body, task_due_at }) =>
      api.patch<ActivityOut>(`/leads/${leadId}/activities/${activityId}`, {
        body,
        task_due_at,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(leadId) });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["my-tasks"] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}

/** DELETE /leads/{id}/activities/{activityId} — delete a task and its file attachments. */
export function useDeleteLeadTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (activityId) =>
      api.delete<void>(`/leads/${leadId}/activities/${activityId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASKS_KEY(leadId) });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["my-tasks"] });
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}
