"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api-client";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { ImportJobOut } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const RUNNING_POLL_MS = 2000;

/** Poll one import job. Active poll only while still running. */
export function useImportJob(jobId: string | null) {
  return useQuery<ImportJobOut>({
    queryKey: ["import-job", jobId],
    queryFn: () => api.get<ImportJobOut>(`/api/import/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data as ImportJobOut | undefined;
      return data?.status === "running" ? RUNNING_POLL_MS : false;
    },
    refetchIntervalInBackground: false,
  });
}

// ---------------------------------------------------------------------------
// Upload — multipart, can't reuse the JSON api-client wrapper
// ---------------------------------------------------------------------------

async function uploadImport(file: File): Promise<ImportJobOut> {
  const supabase = getSupabaseBrowserClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const form = new FormData();
  form.append("file", file);

  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  // Don't set Content-Type — browser fills in `multipart/form-data; boundary=...`

  const res = await fetch(`${API_URL}/api/import/upload`, {
    method: "POST",
    headers,
    body: form,
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, body);
  return body as ImportJobOut;
}

export function useUploadImport() {
  return useMutation<ImportJobOut, ApiError, File>({
    mutationFn: (file) => uploadImport(file),
  });
}

// ---------------------------------------------------------------------------
// confirm-mapping + apply
// ---------------------------------------------------------------------------

export function useConfirmMapping() {
  const qc = useQueryClient();
  return useMutation<
    ImportJobOut,
    ApiError,
    { id: string; mapping: Record<string, string | null> }
  >({
    mutationFn: ({ id, mapping }) =>
      api.post<ImportJobOut>(`/api/import/jobs/${id}/confirm-mapping`, {
        mapping,
      }),
    onSuccess: (data) => {
      qc.setQueryData(["import-job", data.id], data);
    },
  });
}

export function useApplyImport() {
  const qc = useQueryClient();
  return useMutation<ImportJobOut, ApiError, string>({
    mutationFn: (id) => api.post<ImportJobOut>(`/api/import/jobs/${id}/apply`),
    onSuccess: (data) => {
      qc.setQueryData(["import-job", data.id], data);
    },
  });
}
