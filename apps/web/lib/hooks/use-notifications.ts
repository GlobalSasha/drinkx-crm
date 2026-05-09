"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  MarkAllReadOut,
  NotificationListOut,
  NotificationOut,
} from "@/lib/types";

const POLL_MS = 30_000;

/** Poll the bell badge — counts unread on every tick. */
export function useNotificationsBadge() {
  return useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () =>
      api.get<NotificationListOut>("/notifications?unread=true&page=1&page_size=1"),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}

/** Drawer body — list of notifications, optionally filtered to unread. */
export function useNotificationsList(opts: { unread: boolean }) {
  const { unread } = opts;
  return useQuery({
    queryKey: ["notifications", "list", { unread }],
    queryFn: () =>
      api.get<NotificationListOut>(
        `/notifications?unread=${unread ? "true" : "false"}&page=1&page_size=30`,
      ),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<NotificationOut>(`/notifications/${id}/read`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<MarkAllReadOut>("/notifications/mark-all-read"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

/**
 * Permanent dismiss for system / daily-plan rows that don't navigate
 * to a lead (Sprint 2.4 G5). Hard-delete server-side — the row
 * disappears from both filtered views.
 */
export function useDismissNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/notifications/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
