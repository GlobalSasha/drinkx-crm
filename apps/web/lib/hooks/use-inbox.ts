"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  InboxConfirmIn,
  InboxCountOut,
  InboxItemOut,
  InboxPageOut,
} from "@/lib/types";

const COUNT_POLL_MS = 30_000;
const PAGE_SIZE = 20;

/** Sidebar badge — pending items count, polled every 30s. */
export function useInboxCount() {
  return useQuery({
    queryKey: ["inbox", "count"],
    queryFn: () => api.get<InboxCountOut>("/api/inbox/count"),
    refetchInterval: COUNT_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Inbox page body — pending items, paginated. */
export function useInboxPending(page: number = 1) {
  return useQuery({
    queryKey: ["inbox", "pending", page],
    queryFn: () =>
      api.get<InboxPageOut>(
        `/api/inbox?status=pending&page=${page}&page_size=${PAGE_SIZE}`,
      ),
    refetchInterval: COUNT_POLL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useConfirmItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InboxConfirmIn }) =>
      api.post<InboxItemOut>(`/api/inbox/${id}/confirm`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

export function useDismissItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<InboxItemOut>(`/api/inbox/${id}/dismiss`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["inbox"] });
    },
  });
}

/** Start the Gmail OAuth flow — backend returns the consent URL. */
export function useConnectGmail() {
  return useMutation({
    mutationFn: () =>
      api.post<{ redirect_url: string }>("/api/inbox/connect-gmail"),
  });
}
