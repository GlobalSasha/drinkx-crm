"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { NoteOut } from "@/lib/types";

export function useNotes(leadId: string) {
  return useQuery<NoteOut[]>({
    queryKey: ["notes", leadId],
    queryFn: () => api.get<NoteOut[]>(`/leads/${leadId}/notes`),
    enabled: !!leadId,
  });
}

export function useCreateNote(leadId: string) {
  const qc = useQueryClient();
  return useMutation<NoteOut, ApiError, string>({
    mutationFn: (text) => api.post<NoteOut>(`/leads/${leadId}/notes`, { text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", leadId] }),
  });
}

export function useUpdateNote(leadId: string) {
  const qc = useQueryClient();
  return useMutation<NoteOut, ApiError, { noteId: string; text: string }>({
    mutationFn: ({ noteId, text }) =>
      api.patch<NoteOut>(`/leads/${leadId}/notes/${noteId}`, { text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", leadId] }),
  });
}

export function useDeleteNote(leadId: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (noteId) => api.delete<void>(`/leads/${leadId}/notes/${noteId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", leadId] }),
  });
}
