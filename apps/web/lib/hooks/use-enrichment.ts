"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { EnrichmentRun, EnrichmentTriggerResponse } from "@/lib/types";

export function useLatestEnrichment(leadId: string | null | undefined) {
  const qc = useQueryClient();
  // Track previous status so we only invalidate on the running→terminal
  // edge — not on initial mount of a card whose run already finished
  // (the lead prop is already current in that case).
  const prevStatus = useRef<string | undefined>(undefined);

  const query = useQuery({
    queryKey: ["enrichment", leadId, "latest"],
    queryFn: () => api.get<EnrichmentRun | null>(`/leads/${leadId}/enrichment/latest`),
    enabled: Boolean(leadId),
    refetchInterval: (q) => {
      const data = q.state.data as EnrichmentRun | null | undefined;
      return data?.status === "running" ? 2000 : false;
    },
  });

  // The orchestrator writes the brief to `lead.ai_data` independently of
  // this hook's cache. When polling sees the run flip to a terminal
  // state, the lead query is stale — refetch it so DealAndAITab re-renders
  // with the new `ai_data` instead of staying empty until a hard reload.
  useEffect(() => {
    const curr = query.data?.status;
    if (
      prevStatus.current === "running" &&
      (curr === "succeeded" || curr === "failed")
    ) {
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
    }
    prevStatus.current = curr;
  }, [query.data?.status, leadId, qc]);

  return query;
}

export type EnrichmentMode = "full" | "append";

export function useTriggerEnrichment(leadId: string) {
  const qc = useQueryClient();
  return useMutation<EnrichmentTriggerResponse, ApiError, EnrichmentMode | void>({
    mutationFn: (mode) => {
      const m = mode ?? "full";
      return api.post<EnrichmentTriggerResponse>(
        `/leads/${leadId}/enrichment?mode=${m}`,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["enrichment", leadId, "latest"] });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
    },
  });
}
