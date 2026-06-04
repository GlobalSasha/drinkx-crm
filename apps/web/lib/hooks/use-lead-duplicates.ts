"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { LeadOut } from "@/lib/types";

/**
 * Likely duplicates of a lead — same corporate-email domain, phone, or
 * company (backend `GET /leads/{id}/duplicates`, Odoo dedup pattern).
 * Non-destructive: this only surfaces candidates. Gated by `enabled`
 * so we don't fire the query until the manager opens the dup modal.
 */
export function useLeadDuplicates(leadId: string, enabled: boolean) {
  return useQuery<LeadOut[]>({
    queryKey: ["lead-duplicates", leadId],
    queryFn: () => api.get<LeadOut[]>(`/leads/${leadId}/duplicates`),
    enabled: enabled && !!leadId,
    staleTime: 0,
  });
}

/**
 * Merge the chosen duplicate leads INTO this lead (the master). Human-
 * triggered only — the modal collects an explicit selection + confirm
 * before calling this (anti-pattern #4: never auto-merge).
 *
 * On success the backend re-points history, fills the master's empty
 * fields and archives the dups. We invalidate the lead, its feed (the
 * merge writes a `system` audit Activity), the dup list and every lead
 * list so the absorbed rows drop out of the pool/pipeline views.
 */
export function useMergeLeads(leadId: string) {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, string[]>({
    mutationFn: (duplicateIds) =>
      api.post<LeadOut>(`/leads/${leadId}/merge`, { duplicate_ids: duplicateIds }),
    onSuccess: (master) => {
      qc.setQueryData(["lead", leadId], master);
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
      qc.invalidateQueries({ queryKey: ["lead-duplicates", leadId] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
