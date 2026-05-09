// Hooks for the LeadCard custom-fields section — Sprint 2.6 G4.
//
// `useLeadAttributes(leadId)` lists every workspace definition merged
// with this lead's value (null when unset). `useUpsertLeadAttribute`
// posts a single string-typed value; backend parses against the
// definition's kind. Backend echoes the updated row so the cache
// flips without a follow-up GET.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { LeadAttributeOut, LeadAttributeUpsertIn } from "@/lib/types";

const KEY = (leadId: string) => ["lead-attributes", leadId] as const;

export function useLeadAttributes(leadId: string | null | undefined) {
  return useQuery<LeadAttributeOut[]>({
    queryKey: KEY(leadId ?? ""),
    queryFn: () =>
      api.get<LeadAttributeOut[]>(`/leads/${leadId}/attributes`),
    enabled: !!leadId,
    staleTime: 60_000,
  });
}

export function useUpsertLeadAttribute(leadId: string) {
  const qc = useQueryClient();
  return useMutation<LeadAttributeOut, ApiError, LeadAttributeUpsertIn>({
    mutationFn: (body) =>
      api.patch<LeadAttributeOut>(`/leads/${leadId}/attributes`, body),
    onSuccess: (next) => {
      // Splice the updated row into the cached list rather than
      // re-fetching — the backend already returned the merged shape.
      qc.setQueryData<LeadAttributeOut[]>(KEY(leadId), (prev) => {
        if (!prev) return prev;
        return prev.map((r) =>
          r.definition_id === next.definition_id ? next : r,
        );
      });
    },
  });
}
