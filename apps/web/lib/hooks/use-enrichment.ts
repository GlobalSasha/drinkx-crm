"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { EnrichmentRun, EnrichmentTriggerResponse } from "@/lib/types";

export function useLatestEnrichment(leadId: string | null | undefined) {
  return useQuery({
    queryKey: ["enrichment", leadId, "latest"],
    queryFn: () => api.get<EnrichmentRun | null>(`/leads/${leadId}/enrichment/latest`),
    enabled: Boolean(leadId),
    refetchInterval: (q) => {
      const data = q.state.data as EnrichmentRun | null | undefined;
      return data?.status === "running" ? 2000 : false;
    },
  });
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
