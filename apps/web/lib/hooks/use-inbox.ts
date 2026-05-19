"use client";

// Sprint 3.7: /inbox Gmail triage retired. useInboxCount, useInboxPending,
// useConfirmItem, useDismissItem removed — /inbox page deleted.
// InboxItem model kept on backend for audit only.
// auto_create_lead_from_email is the new email entry-point (see processor.py).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  InboxMessageOut,
} from "@/lib/types";

interface InboxUnmatchedMessagesOut {
  items: InboxMessageOut[];
  total: number;
}

/** Start the Gmail OAuth flow — backend returns the consent URL.
 * Error type is ApiError so callers can distinguish 503
 * «not configured» (GOOGLE_CLIENT_ID missing) from other failures. */
export function useConnectGmail() {
  return useMutation<{ redirect_url: string }, ApiError, void>({
    mutationFn: () =>
      api.post<{ redirect_url: string }>("/api/inbox/connect-gmail"),
  });
}

// ---- Multi-channel inbox — unmatched messages (Sprint 3.4 G7) ----

const UNMATCHED_POLL_MS = 15_000;
const UNMATCHED_PAGE_SIZE = 50;

/** Telegram / MAX / phone messages that arrived without a matched lead. */
export function useInboxUnmatchedMessages(page: number = 1) {
  return useQuery({
    queryKey: ["inbox", "unmatched-messages", page],
    queryFn: () =>
      api.get<InboxUnmatchedMessagesOut>(
        `/api/inbox/unmatched/messages?page=${page}&page_size=${UNMATCHED_PAGE_SIZE}`,
      ),
    refetchInterval: UNMATCHED_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Attach an unmatched InboxMessage to a lead. */
export function useAssignInboxMessage() {
  const qc = useQueryClient();
  return useMutation<
    InboxMessageOut,
    ApiError,
    { id: string; lead_id: string }
  >({
    mutationFn: ({ id, lead_id }) =>
      api.patch<InboxMessageOut>(`/api/inbox/messages/${id}/assign`, {
        lead_id,
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["inbox", "unmatched-messages"] });
      // The lead's feed gets a new entry — refresh if open.
      qc.invalidateQueries({
        queryKey: ["lead-inbox", vars.lead_id],
      });
    },
  });
}
