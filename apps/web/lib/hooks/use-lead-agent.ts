"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentRefreshResponse,
  AgentSuggestionResponse,
} from "@/lib/types";

/**
 * GET /leads/{id}/agent/suggestion — read the cached banner content.
 * Cheap, never hits the LLM. Refresh via `useRefreshSuggestion`.
 */
export function useAgentSuggestion(leadId: string) {
  return useQuery({
    queryKey: ["lead-agent", "suggestion", leadId],
    queryFn: () =>
      api.get<AgentSuggestionResponse>(`/leads/${leadId}/agent/suggestion`),
    enabled: !!leadId,
  });
}

/**
 * POST /leads/{id}/agent/suggestion/refresh — queue a Celery refresh.
 * Frontend re-fetches the cached suggestion after a short polling
 * window. Returns 202 immediately.
 */
export function useRefreshSuggestion(leadId: string) {
  const qc = useQueryClient();
  return useMutation<AgentRefreshResponse, ApiError, void>({
    mutationFn: () =>
      api.post<AgentRefreshResponse>(`/leads/${leadId}/agent/suggestion/refresh`),
    onSuccess: () => {
      // Re-poll the cached suggestion a few seconds later — gives
      // the worker time to finish before we re-read the row.
      setTimeout(() => {
        qc.invalidateQueries({
          queryKey: ["lead-agent", "suggestion", leadId],
        });
      }, 4000);
    },
  });
}

/**
 * POST /leads/{id}/agent/chat — Sales Coach turn.
 * Synchronous from the caller's perspective — the runner blocks on
 * the LLM. On any failure the backend returns a polite Russian
 * fallback string in `reply`, so the chat drawer never breaks.
 */
export function useAgentChat(leadId: string) {
  return useMutation<AgentChatResponse, ApiError, AgentChatRequest>({
    mutationFn: (body) =>
      api.post<AgentChatResponse>(`/leads/${leadId}/agent/chat`, body),
  });
}
