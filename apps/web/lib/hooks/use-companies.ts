"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  CompanyCardOut,
  CompanyCreate,
  CompanyListOut,
  CompanyOut,
  CompanyUpdate,
} from "@/lib/types";

export function useCompany(id: string | null | undefined) {
  return useQuery<CompanyCardOut>({
    queryKey: ["company", id],
    queryFn: () => api.get<CompanyCardOut>(`/companies/${id}`),
    enabled: Boolean(id),
  });
}

export function useCompanies(params?: {
  city?: string;
  primary_segment?: string;
  is_archived?: boolean;
}) {
  const qs = new URLSearchParams();
  if (params?.city) qs.set("city", params.city);
  if (params?.primary_segment) qs.set("primary_segment", params.primary_segment);
  if (params?.is_archived !== undefined)
    qs.set("is_archived", String(params.is_archived));
  const suffix = qs.toString();
  return useQuery<CompanyListOut>({
    queryKey: ["companies", params],
    queryFn: () => api.get<CompanyListOut>(`/companies${suffix ? "?" + suffix : ""}`),
  });
}

export function useCreateCompany() {
  const qc = useQueryClient();
  return useMutation<CompanyOut, ApiError, { payload: CompanyCreate; force?: boolean }>({
    mutationFn: ({ payload, force }) =>
      api.post<CompanyOut>(
        `/companies${force ? "?force=true" : ""}`,
        payload,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
  });
}

export function useUpdateCompany(id: string) {
  const qc = useQueryClient();
  return useMutation<CompanyOut, ApiError, CompanyUpdate>({
    mutationFn: (body) => api.patch<CompanyOut>(`/companies/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["company", id] });
      qc.invalidateQueries({ queryKey: ["companies"] });
      // Renaming a company propagates to lead.company_name — bust the
      // leads cache so the list/card refetch picks it up.
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useArchiveCompany() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/companies/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
  });
}

export function useMergeCompanies() {
  const qc = useQueryClient();
  return useMutation<
    CompanyOut,
    ApiError,
    { sourceId: string; targetId: string; force?: boolean }
  >({
    mutationFn: ({ sourceId, targetId, force }) =>
      api.post<CompanyOut>(
        `/companies/${sourceId}/merge-into/${targetId}${force ? "?force=true" : ""}`,
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["company", vars.targetId] });
      qc.invalidateQueries({ queryKey: ["company", vars.sourceId] });
      qc.invalidateQueries({ queryKey: ["companies"] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
