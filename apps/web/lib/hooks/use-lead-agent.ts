"use client";

// Lead AI Agent hooks — Sprint 3.1 Phase D.
//
// Three queries, mirroring the backend's three endpoints
// (`apps/api/app/lead_agent/routers.py`):
//
//   useAgentSuggestion(leadId)         — GET  /leads/{id}/agent/suggestion
//   useRefreshAgentSuggestion(leadId)  — POST /leads/{id}/agent/suggestion/refresh
//   useAgentChat(leadId)               — POST /leads/{id}/agent/chat
//
// `useAgentSuggestion` polls every 5s while a refresh is in-flight
// (the optimistic flag flips for ~10s after the mutation triggers,
// then settles). The refresh response itself is fire-and-forget —
// the runner's result lands in `lead.agent_state` and the GET picks
// it up on the next poll tick.

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api-client";
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentSuggestionResponse,
} from "@/lib/types";

const SUGGESTION_KEY = (leadId: string) => ["lead-agent", leadId, "suggestion"] as const;

export function useAgentSuggestion(leadId: string | null | undefined) {
  return useQuery<AgentSuggestionResponse>({
    queryKey: leadId ? SUGGESTION_KEY(leadId) : ["lead-agent", "disabled"],
    queryFn: () =>
      api.get<AgentSuggestionResponse>(`/leads/${leadId}/agent/suggestion`),
    enabled: Boolean(leadId),
    staleTime: 30_000,
  });
}

export function useRefreshAgentSuggestion(leadId: string) {
  const qc = useQueryClient();
  // Local poll latch — we don't have an enrichment-style `status`
  // field on the suggestion endpoint, so flip a ref for ~12s after
  // POST and let the consumer trigger short-interval refetches.
  const pollUntilRef = useRef<number>(0);

  const mutation = useMutation<{ status: string; lead_id: string }, ApiError, void>({
    mutationFn: () =>
      api.post<{ status: string; lead_id: string }>(
        `/leads/${leadId}/agent/suggestion/refresh`,
      ),
    onSuccess: () => {
      pollUntilRef.current = Date.now() + 12_000;
      qc.invalidateQueries({ queryKey: SUGGESTION_KEY(leadId) });
    },
  });

  // Re-fetch every 3s while the latch is open. useEffect runs after
  // each successful mutation tick so the latch reset triggers a
  // fresh interval.
  useEffect(() => {
    if (!mutation.isSuccess) return;
    const interval = setInterval(() => {
      if (Date.now() > pollUntilRef.current) {
        clearInterval(interval);
        return;
      }
      qc.invalidateQueries({ queryKey: SUGGESTION_KEY(leadId) });
    }, 3000);
    return () => clearInterval(interval);
  }, [mutation.isSuccess, leadId, qc]);

  return mutation;
}

export function useAgentChat(leadId: string) {
  return useMutation<AgentChatResponse, ApiError, AgentChatRequest>({
    mutationFn: (body) =>
      api.post<AgentChatResponse>(`/leads/${leadId}/agent/chat`, body),
  });
}
