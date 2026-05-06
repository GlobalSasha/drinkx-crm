import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { FollowupOut, FollowupCreate, FollowupUpdate } from "@/lib/types";

export function useFollowups(leadId: string) {
  return useQuery<FollowupOut[]>({
    queryKey: ["followups", leadId],
    queryFn: () => api.get<FollowupOut[]>(`/leads/${leadId}/followups`),
    enabled: !!leadId,
  });
}

export function useCreateFollowup(leadId: string) {
  const qc = useQueryClient();
  return useMutation<FollowupOut, ApiError, FollowupCreate>({
    mutationFn: (body) =>
      api.post<FollowupOut>(`/leads/${leadId}/followups`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["followups", leadId] });
    },
  });
}

export function useUpdateFollowup(leadId: string, fuId: string) {
  const qc = useQueryClient();
  return useMutation<FollowupOut, ApiError, FollowupUpdate>({
    mutationFn: (body) =>
      api.patch<FollowupOut>(`/leads/${leadId}/followups/${fuId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["followups", leadId] });
    },
  });
}

export function useDeleteFollowup(leadId: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (fuId) =>
      api.delete<void>(`/leads/${leadId}/followups/${fuId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["followups", leadId] });
    },
  });
}

export function useCompleteFollowup(leadId: string) {
  const qc = useQueryClient();
  return useMutation<FollowupOut, ApiError, string>({
    mutationFn: (fuId) =>
      api.post<FollowupOut>(`/leads/${leadId}/followups/${fuId}/complete`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["followups", leadId] });
    },
  });
}
