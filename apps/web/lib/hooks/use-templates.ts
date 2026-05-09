// Hooks for Settings → «Шаблоны» — Sprint 2.4 G4.
//
// Read-open to all roles (managers will preview templates inside the
// Automation Builder in 2.5); write actions are admin-only at the
// backend, the section component just hides the buttons for non-admins.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  MessageTemplateCreate,
  MessageTemplateOut,
  MessageTemplateUpdate,
} from "@/lib/types";

const KEY = ["templates"] as const;

export function useTemplates() {
  return useQuery<MessageTemplateOut[]>({
    queryKey: KEY,
    queryFn: () => api.get<MessageTemplateOut[]>("/templates"),
    staleTime: 60_000,
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation<MessageTemplateOut, ApiError, MessageTemplateCreate>({
    mutationFn: (body) =>
      api.post<MessageTemplateOut>("/templates", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useUpdateTemplate(id: string) {
  const qc = useQueryClient();
  return useMutation<MessageTemplateOut, ApiError, MessageTemplateUpdate>({
    mutationFn: (body) =>
      api.patch<MessageTemplateOut>(`/templates/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/templates/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
