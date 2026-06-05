"use client";

// «Входящие заявки» — website-leads inbox (form submissions).
// Named "incoming" on the frontend to avoid colliding with the existing
// messenger/email `inbox` domain (use-inbox.ts). Backend lives under the
// forms router: /api/forms/inbox*.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { InboxBadgeOut, InboxPageOut } from "@/lib/types";

const POLL_MS = 30_000;

/** Sidebar badge — count of new (unseen) website submissions. Polled. */
export function useIncomingBadge() {
  return useQuery({
    queryKey: ["incoming", "badge"],
    queryFn: () => api.get<InboxBadgeOut>("/api/forms/inbox/badge"),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Incoming list, optionally filtered by form (channel) or to unseen only. */
export function useIncoming(opts: { formId?: string | null; unseenOnly?: boolean }) {
  const { formId = null, unseenOnly = false } = opts;
  return useQuery({
    queryKey: ["incoming", "list", { formId, unseenOnly }],
    queryFn: () => {
      const p = new URLSearchParams({ page: "1", page_size: "50" });
      if (formId) p.set("form_id", formId);
      if (unseenOnly) p.set("unseen_only", "true");
      return api.get<InboxPageOut>(`/api/forms/inbox?${p.toString()}`);
    },
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Advance the seen marker → resets the badge to 0. */
export function useMarkIncomingSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<InboxBadgeOut>("/api/forms/inbox/seen"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["incoming"] });
    },
  });
}
