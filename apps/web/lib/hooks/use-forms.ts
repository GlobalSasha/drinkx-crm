"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api-client";
import type {
  WebFormCreateIn,
  WebFormOut,
  WebFormPageOut,
  WebFormUpdateIn,
} from "@/lib/types";

/** List forms in the current workspace. */
export function useForms() {
  return useQuery<WebFormPageOut>({
    queryKey: ["forms", "list"],
    queryFn: () => api.get<WebFormPageOut>("/api/forms?page=1&page_size=100"),
  });
}

/** One form by id — used by the FormEditor when editing existing. */
export function useForm(id: string | null) {
  return useQuery<WebFormOut>({
    queryKey: ["form", id],
    queryFn: () => api.get<WebFormOut>(`/api/forms/${id}`),
    enabled: !!id,
  });
}

export function useCreateForm() {
  const qc = useQueryClient();
  return useMutation<WebFormOut, ApiError, WebFormCreateIn>({
    mutationFn: (body) => api.post<WebFormOut>("/api/forms", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["forms"] });
    },
  });
}

export function useUpdateForm() {
  const qc = useQueryClient();
  return useMutation<
    WebFormOut,
    ApiError,
    { id: string; body: WebFormUpdateIn }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<WebFormOut>(`/api/forms/${id}`, body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["forms"] });
      qc.setQueryData(["form", data.id], data);
    },
  });
}

export function useDeleteForm() {
  const qc = useQueryClient();
  return useMutation<WebFormOut, ApiError, string>({
    mutationFn: (id) => api.delete<WebFormOut>(`/api/forms/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["forms"] });
    },
  });
}

/** Inline-toggle in the list — no modal. PATCH with just `is_active`. */
export function useToggleFormActive() {
  const qc = useQueryClient();
  return useMutation<
    WebFormOut,
    ApiError,
    { id: string; is_active: boolean }
  >({
    mutationFn: ({ id, is_active }) =>
      api.patch<WebFormOut>(`/api/forms/${id}`, { is_active }),
    onMutate: async ({ id, is_active }) => {
      // Optimistic flip in the list cache so the toggle feels instant.
      await qc.cancelQueries({ queryKey: ["forms", "list"] });
      const prev = qc.getQueryData<WebFormPageOut>(["forms", "list"]);
      if (prev) {
        qc.setQueryData<WebFormPageOut>(["forms", "list"], {
          ...prev,
          items: prev.items.map((f) =>
            f.id === id ? { ...f, is_active } : f,
          ),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, context) => {
      const prev = (context as { prev?: WebFormPageOut } | undefined)?.prev;
      if (prev) qc.setQueryData(["forms", "list"], prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["forms"] });
    },
  });
}
