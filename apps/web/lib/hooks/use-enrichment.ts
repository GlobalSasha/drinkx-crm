"use client";

import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { EnrichmentRun, EnrichmentTriggerResponse } from "@/lib/types";

export function useLatestEnrichment(leadId: string | null | undefined) {
  const qc = useQueryClient();
  // Refresh after a running job finishes, including a new job that completed
  // before the first poll. Opening an old finished run needs no invalidation.
  const previous = useRef<{ leadId: string | null | undefined; id?: string; status?: string } | undefined>(undefined);

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
    const curr = query.data;
    const prev = previous.current;
    if (
      prev && prev.leadId === leadId &&
      (prev.status === "running" || prev.id !== curr?.id) &&
      (curr?.status === "succeeded" || curr?.status === "failed")
    ) {
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["contacts", leadId] });
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    }
    if (query.data !== undefined) {
      previous.current = { leadId, id: curr?.id, status: curr?.status };
    }
  }, [query.data, leadId, qc]);

  return query;
}

export type EnrichmentMode = "full" | "append" | "lightweight";

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
