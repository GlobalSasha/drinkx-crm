"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api-client";
import type {
  IngestConflictOut,
  IngestJobOut,
  ResolveConflictIn,
} from "@/lib/types";

const POLL_MS = 2000;
const POLLING_STATUSES = new Set<string>([
  "pending",
  "extracting",
  "matching",
  "resolving",
]);

// ----- queries -----

export function useIngestJob(jobId: string | null) {
  return useQuery<IngestJobOut>({
    queryKey: ["base-update-job", jobId],
    queryFn: () => api.get<IngestJobOut>(`/api/base-update/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = (query.state.data as IngestJobOut | undefined)?.status;
      return status && POLLING_STATUSES.has(status) ? POLL_MS : false;
    },
    refetchIntervalInBackground: false,
  });
}

export function useIngestJobConflicts(jobId: string | null, onlyOpen = true) {
  return useQuery<IngestConflictOut[]>({
    queryKey: ["base-update-conflicts", jobId, onlyOpen],
    queryFn: () =>
      api.get<IngestConflictOut[]>(
        `/api/base-update/jobs/${jobId}/conflicts?only_open=${onlyOpen}`,
      ),
    enabled: !!jobId,
  });
}

export function useIngestJobs(limit = 20) {
  return useQuery<IngestJobOut[]>({
    queryKey: ["base-update-jobs", limit],
    queryFn: () =>
      api.get<IngestJobOut[]>(`/api/base-update/jobs?limit=${limit}`),
  });
}

// ----- mutations -----

export function useCreateIngestJob() {
  const qc = useQueryClient();
  return useMutation<IngestJobOut, ApiError, File[]>({
    mutationFn: async (files) => {
      // Multipart upload — uses api.postFormData (added to api-client).
      // Do NOT set Content-Type; the browser fills in the multipart boundary.
      const form = new FormData();
      for (const f of files) form.append("files", f);
      return api.postFormData<IngestJobOut>("/api/base-update/jobs", form);
    },
    onSuccess: (job) => {
      qc.setQueryData(["base-update-job", job.id], job);
      qc.invalidateQueries({ queryKey: ["base-update-jobs"] });
    },
  });
}

export function useResolveConflict(jobId: string | null) {
  const qc = useQueryClient();
  return useMutation<
    IngestConflictOut,
    ApiError,
    { conflictId: string; body: ResolveConflictIn }
  >({
    mutationFn: ({ conflictId, body }) =>
      api.patch<IngestConflictOut>(
        `/api/base-update/conflicts/${conflictId}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["base-update-conflicts", jobId] });
      qc.invalidateQueries({ queryKey: ["base-update-job", jobId] });
    },
  });
}

export function useApplyResolutions(jobId: string | null) {
  const qc = useQueryClient();
  return useMutation<IngestJobOut, ApiError, void>({
    mutationFn: () =>
      api.post<IngestJobOut>(`/api/base-update/jobs/${jobId}/apply`),
    onSuccess: (job) => {
      qc.setQueryData(["base-update-job", job.id], job);
    },
  });
}
