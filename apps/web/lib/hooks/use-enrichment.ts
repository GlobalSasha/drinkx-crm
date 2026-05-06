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

export function useTriggerEnrichment(leadId: string) {
  const qc = useQueryClient();
  return useMutation<EnrichmentTriggerResponse, ApiError>({
    mutationFn: () => api.post<EnrichmentTriggerResponse>(`/leads/${leadId}/enrichment`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["enrichment", leadId, "latest"] });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
    },
  });
}
