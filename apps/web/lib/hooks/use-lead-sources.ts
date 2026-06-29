import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { LeadSource, LeadSourceCreate, LeadSourceUpdate } from "@/lib/types";

const KEY = ["lead-sources"] as const;

/** Workspace lead-source dictionary. `activeOnly` for the lead-create form. */
export function useLeadSources(activeOnly = false) {
  return useQuery({
    queryKey: [...KEY, { activeOnly }],
    queryFn: () =>
      api.get<LeadSource[]>(`/lead-sources${activeOnly ? "?active_only=true" : ""}`),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateLeadSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadSourceCreate) =>
      api.post<LeadSource>("/lead-sources", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateLeadSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: LeadSourceUpdate }) =>
      api.patch<LeadSource>(`/lead-sources/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteLeadSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/lead-sources/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
