"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api-client";
import type { ExportJobOut, ExportRequestIn } from "@/lib/types";

const RUNNING_POLL_MS = 2000;

/** Poll one export job. Active poll only while pending or running. */
export function useExportJob(jobId: string | null) {
  return useQuery<ExportJobOut>({
    queryKey: ["export-job", jobId],
    queryFn: () => api.get<ExportJobOut>(`/api/export/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data as ExportJobOut | undefined;
      const status = data?.status;
      return status === "pending" || status === "running"
        ? RUNNING_POLL_MS
        : false;
    },
    refetchIntervalInBackground: false,
  });
}

export function useCreateExport() {
  const qc = useQueryClient();
  return useMutation<ExportJobOut, ApiError, ExportRequestIn>({
    mutationFn: (body) => api.post<ExportJobOut>("/api/export", body),
    onSuccess: (data) => {
      qc.setQueryData(["export-job", data.id], data);
    },
  });
}

/** Lazy-load the canonical AI bulk-update prompt. Server-side constant
 *  — staleTime=Infinity so we don't re-fetch on every modal open. */
export function useBulkUpdatePrompt(enabled: boolean = true) {
  return useQuery<{ prompt: string }>({
    queryKey: ["bulk-update-prompt"],
    queryFn: () => api.get<{ prompt: string }>("/api/export/bulk-update-prompt"),
    enabled,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}
