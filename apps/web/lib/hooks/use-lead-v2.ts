"use client";

// Lead Card v2 sprint hooks — stage durations, deal-value PATCH,
// score-details GET + PATCH. Lives in its own file so it doesn't
// bloat the already-large `use-lead.ts`.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  DealPatchIn,
  LeadOut,
  ScoreBreakdownOut,
  StageDurationOut,
} from "@/lib/types";

/** GET /leads/{id}/stage-durations — read-only, used by StagesStepper. */
export function useStageDurations(leadId: string) {
  return useQuery<StageDurationOut[]>({
    queryKey: ["stage-durations", leadId],
    queryFn: () =>
      api.get<StageDurationOut[]>(`/leads/${leadId}/stage-durations`),
    enabled: !!leadId,
    staleTime: 30_000,
  });
}

/** PATCH /leads/{id}/deal — updates the deal-value strip. */
export function useUpdateDealFields(leadId: string) {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, DealPatchIn>({
    mutationFn: (body) => api.patch<LeadOut>(`/leads/${leadId}/deal`, body),
    onSuccess: (lead) => {
      qc.setQueryData(["lead", leadId], lead);
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

/** GET /leads/{id}/score-details — drives the breakdown popup. */
export function useScoreBreakdown(leadId: string, enabled: boolean) {
  return useQuery<ScoreBreakdownOut>({
    queryKey: ["score-breakdown", leadId],
    queryFn: () =>
      api.get<ScoreBreakdownOut>(`/leads/${leadId}/score-details`),
    enabled: !!leadId && enabled,
    staleTime: 0,
  });
}

/** PATCH /leads/{id}/score-details — manual edit of the criteria grid.
 *
 *  Body: `{ score_details: { key: 0..max_value, ... } }`. Server
 *  recomputes `leads.score` + `leads.priority` and returns the full
 *  LeadOut. We seed the result into the `lead` query cache so the
 *  header pill / score card updates without a refetch. The
 *  `score-breakdown` query is invalidated separately so the popup
 *  picks up the new contributions on next open.
 */
export function useUpdateScoreDetails(leadId: string) {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, Record<string, number>>({
    mutationFn: (score_details) =>
      api.patch<LeadOut>(`/leads/${leadId}/score-details`, { score_details }),
    onSuccess: (lead) => {
      qc.setQueryData(["lead", leadId], lead);
      qc.invalidateQueries({ queryKey: ["score-breakdown", leadId] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
