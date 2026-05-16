"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { AskChakOut, FeedItemOut, FeedListOut } from "@/lib/types";

/**
 * Cursor-paginated unified activity feed for a lead.
 *
 * - First page: `GET /leads/{id}/feed?limit=50`
 * - Next page: cursor returned in `next_cursor`
 * - `items` flattens all pages so the component renders a single list
 */
export function useFeed(leadId: string, limit = 50) {
  return useInfiniteQuery({
    queryKey: ["feed", leadId],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: String(limit) });
      if (pageParam) params.set("cursor", pageParam);
      return api.get<FeedListOut>(`/leads/${leadId}/feed?${params.toString()}`);
    },
    getNextPageParam: (last) => last.next_cursor,
    enabled: !!leadId,
    staleTime: 10_000,
  });
}

/**
 * Mark a task-type activity as completed. Backend already supports
 * `POST /leads/{lead_id}/activities/{id}/complete-task` — we reuse
 * it rather than introducing a parallel PATCH endpoint.
 *
 * Optimistic: flips `task_done = true` + sets `task_completed_at`
 * in the feed cache immediately. Rolls back on error.
 */
export function useCompleteTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<FeedItemOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<FeedItemOut>(
        `/leads/${leadId}/activities/${activityId}/complete-task`,
      ),
    onMutate: async (activityId) => {
      await qc.cancelQueries({ queryKey: ["feed", leadId] });
      const prev = qc.getQueryData(["feed", leadId]);
      qc.setQueryData(["feed", leadId], (data: unknown) => {
        if (!data || typeof data !== "object") return data;
        const d = data as { pages?: FeedListOut[] };
        if (!d.pages) return data;
        return {
          ...d,
          pages: d.pages.map((p) => ({
            ...p,
            items: p.items.map((it) =>
              it.id === activityId
                ? {
                    ...it,
                    task_done: true,
                    task_completed_at: new Date().toISOString(),
                  }
                : it,
            ),
          })),
        };
      });
      return { prev };
    },
    onError: (_err, _vars, context) => {
      const ctx = context as { prev?: unknown } | undefined;
      if (ctx?.prev !== undefined) qc.setQueryData(["feed", leadId], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}

/**
 * Send a question to Чак. The backend writes both the question
 * (as `comment`) and the answer (as `ai_suggestion`) into the feed.
 * We prepend both to the cache so the user sees them appear without
 * a refetch.
 */
export function useAskChak(leadId: string) {
  const qc = useQueryClient();
  return useMutation<AskChakOut, ApiError, string>({
    mutationFn: (question) =>
      api.post<AskChakOut>(`/leads/${leadId}/feed/ask-chak`, { question }),
    onSuccess: ({ question_activity, answer_activity }) => {
      qc.setQueryData(["feed", leadId], (data: unknown) => {
        if (!data || typeof data !== "object") return data;
        const d = data as { pages?: FeedListOut[] };
        if (!d.pages || d.pages.length === 0) return data;
        const firstPage = d.pages[0];
        // Answer is newer than question (committed second on server),
        // so it comes first in DESC order.
        const newFirstItems = [
          answer_activity,
          question_activity,
          ...firstPage.items,
        ];
        return {
          ...d,
          pages: [{ ...firstPage, items: newFirstItems }, ...d.pages.slice(1)],
        };
      });
    },
  });
}

/**
 * Create a generic activity (comment / task / call / file).
 *
 * Backend: `POST /leads/{id}/activities`. The composer drives all
 * four types through this single mutation by passing the right
 * `type` + per-type fields.
 */
export interface CreateActivityIn {
  type: "comment" | "task" | "phone" | "file";
  body?: string | null;
  task_due_at?: string | null;
  file_url?: string | null;
  file_kind?: string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload_json?: Record<string, any>;
}

export function useCreateActivity(leadId: string) {
  const qc = useQueryClient();
  return useMutation<FeedItemOut, ApiError, CreateActivityIn>({
    mutationFn: (body) =>
      api.post<FeedItemOut>(`/leads/${leadId}/activities`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}
