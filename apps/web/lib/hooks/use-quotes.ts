"use client";

// Quote / КП hooks (Phase 3). Backend: Phase 2 routers (PR #136).
// All endpoints are workspace-scoped and open to any authed role.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  QuoteCreate,
  QuoteListItemOut,
  QuoteOut,
  QuoteStatus,
  QuoteUpdate,
} from "@/lib/types";

const listKey = (leadId: string) => ["quotes", "list", leadId] as const;
const detailKey = (quoteId: string) => ["quotes", "detail", quoteId] as const;

export function useLeadQuotes(leadId: string) {
  return useQuery<QuoteListItemOut[]>({
    queryKey: listKey(leadId),
    queryFn: () => api.get<QuoteListItemOut[]>(`/api/leads/${leadId}/quotes`),
    enabled: !!leadId,
  });
}

export function useQuote(quoteId: string | null) {
  return useQuery<QuoteOut>({
    queryKey: detailKey(quoteId ?? ""),
    queryFn: () => api.get<QuoteOut>(`/api/quotes/${quoteId}`),
    enabled: !!quoteId,
  });
}

export function useCreateQuote(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: QuoteCreate = {}) =>
      api.post<QuoteOut>(`/api/leads/${leadId}/quotes`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(leadId) }),
  });
}

export function useUpdateQuote(leadId: string, quoteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: QuoteUpdate) =>
      api.patch<QuoteOut>(`/api/quotes/${quoteId}`, body),
    onSuccess: (data) => {
      qc.setQueryData(detailKey(quoteId), data);
      qc.invalidateQueries({ queryKey: listKey(leadId) });
    },
  });
}

export function useSetQuoteStatus(leadId: string, quoteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: QuoteStatus) =>
      api.post<QuoteOut>(`/api/quotes/${quoteId}/status`, { status }),
    onSuccess: (data) => {
      qc.setQueryData(detailKey(quoteId), data);
      qc.invalidateQueries({ queryKey: listKey(leadId) });
    },
  });
}

export function useDeleteQuote(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (quoteId: string) => api.delete(`/api/quotes/${quoteId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(leadId) }),
  });
}
