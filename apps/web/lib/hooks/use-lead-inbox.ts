"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  InboxCallIn,
  InboxCallOut,
  InboxFeedOut,
  InboxMessageOut,
  InboxSendIn,
} from "@/lib/types";

const FEED_POLL_MS = 10_000;

/**
 * GET /leads/{lead_id}/inbox — merged feed (email + telegram + max + phone).
 * Polls every 10s while the lead card is visible.
 */
export function useLeadInbox(leadId: string) {
  return useQuery({
    queryKey: ["lead-inbox", leadId],
    queryFn: () => api.get<InboxFeedOut>(`/leads/${leadId}/inbox`),
    refetchInterval: FEED_POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}

/**
 * POST /leads/{lead_id}/inbox/send — outbound message.
 * Used for telegram (G2), phone is via useLeadInboxCall, email is G5.
 */
export function useLeadInboxSend(leadId: string) {
  const qc = useQueryClient();
  return useMutation<InboxMessageOut, ApiError, InboxSendIn>({
    mutationFn: (body) =>
      api.post<InboxMessageOut>(`/leads/${leadId}/inbox/send`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead-inbox", leadId] });
      // The send also writes an Activity row — refresh the activity tab too.
      qc.invalidateQueries({ queryKey: ["lead-activities", leadId] });
    },
  });
}

/**
 * POST /leads/{lead_id}/inbox/call — click-to-call (Mango).
 * No InboxMessage row is written here — Mango sends call_end shortly
 * after and the feed picks it up via polling.
 */
export function useLeadInboxCall(leadId: string) {
  return useMutation<InboxCallOut, ApiError, InboxCallIn>({
    mutationFn: (body) =>
      api.post<InboxCallOut>(`/leads/${leadId}/inbox/call`, body),
  });
}
