import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  CompanySummary,
  CompanyAttention,
  CompanyManagers,
  ManagerPeriod,
} from "@/lib/types";

/** Company overview — incoming-lead pulse + sources + daily. Admin/head only. */
export function useCompanySummary(period: "week" | "month" = "week") {
  return useQuery({
    queryKey: ["company-summary", period],
    queryFn: () => api.get<CompanySummary>(`/company/summary?period=${period}`),
    staleTime: 60 * 1000,
  });
}

export function useCompanyAttention() {
  return useQuery({
    queryKey: ["company-attention"],
    queryFn: () => api.get<CompanyAttention>("/company/attention"),
    staleTime: 60 * 1000,
  });
}

/** Per-manager work + result metrics for the CEO /today. Admin/head only. */
export function useCompanyManagers(period: ManagerPeriod = "week") {
  return useQuery({
    queryKey: ["company-managers", period],
    queryFn: () => api.get<CompanyManagers>(`/company/managers?period=${period}`),
    staleTime: 60 * 1000,
  });
}
