import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { CompanySummary, CompanyAttention } from "@/lib/types";

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
