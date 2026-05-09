// Hooks for Settings → «Кастомные поля» — Sprint 2.4 G3.
//
// Definition CRUD only in v1. Rendering the values on LeadCard /
// pipeline filters / segments is a 2.4+ polish carryover.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  CustomAttributeDefinitionCreateIn,
  CustomAttributeDefinitionOut,
  CustomAttributeDefinitionUpdateIn,
} from "@/lib/types";

const KEY = ["custom-attributes"] as const;

export function useCustomAttributes() {
  return useQuery<CustomAttributeDefinitionOut[]>({
    queryKey: KEY,
    queryFn: () =>
      api.get<CustomAttributeDefinitionOut[]>("/custom-attributes"),
    staleTime: 60_000,
  });
}

export function useCreateCustomAttribute() {
  const qc = useQueryClient();
  return useMutation<
    CustomAttributeDefinitionOut,
    ApiError,
    CustomAttributeDefinitionCreateIn
  >({
    mutationFn: (body) =>
      api.post<CustomAttributeDefinitionOut>("/custom-attributes", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useUpdateCustomAttribute(id: string) {
  const qc = useQueryClient();
  return useMutation<
    CustomAttributeDefinitionOut,
    ApiError,
    CustomAttributeDefinitionUpdateIn
  >({
    mutationFn: (body) =>
      api.patch<CustomAttributeDefinitionOut>(
        `/custom-attributes/${id}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeleteCustomAttribute() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/custom-attributes/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
