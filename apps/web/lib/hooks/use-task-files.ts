import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { SignedDownloadOut, TaskFileOut } from "@/lib/types";

/** List files attached to a specific task with an optional ILIKE filter on filename + body. */
export function useTaskFiles(leadId: string, taskId: string, q?: string) {
  return useQuery<TaskFileOut[]>({
    queryKey: ["task-files", leadId, taskId, q ?? ""],
    queryFn: () =>
      api.get<TaskFileOut[]>(
        `/leads/${leadId}/tasks/${taskId}/files${q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`,
      ),
    enabled: !!leadId && !!taskId,
  });
}

/** Multipart upload via api.postFormData. Browser sets the boundary; bearer is attached automatically. */
export function useUploadTaskFile(leadId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation<TaskFileOut, Error, { file: File; caption?: string }>({
    mutationFn: async ({ file, caption }) => {
      const form = new FormData();
      form.append("file", file);
      if (caption) form.append("caption", caption);
      return await api.postFormData<TaskFileOut>(
        `/leads/${leadId}/tasks/${taskId}/files`,
        form,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-files", leadId, taskId] });
      // File activities also land in the lead's feed
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}

/** Upload a file as a lead-level feed attachment (no parent task). */
export function useUploadLeadFile(leadId: string) {
  const qc = useQueryClient();
  return useMutation<TaskFileOut, Error, { file: File; caption?: string }>({
    mutationFn: async ({ file, caption }) => {
      const form = new FormData();
      form.append("file", file);
      if (caption) form.append("caption", caption);
      return await api.postFormData<TaskFileOut>(`/leads/${leadId}/files`, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}

/** Fetch a 5-minute signed URL for an existing file Activity. */
export function useDownloadTaskFile() {
  return useMutation<SignedDownloadOut, Error, string>({
    mutationFn: (activityId) => api.get<SignedDownloadOut>(`/activities/${activityId}/download`),
  });
}

/** Best-effort delete (storage + Activity row). Invalidates the task-files list and the feed. */
export function useDeleteTaskFile(leadId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (activityId) => api.delete<void>(`/activities/${activityId}/file`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-files", leadId, taskId] });
      qc.invalidateQueries({ queryKey: ["feed", leadId] });
    },
  });
}
