import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  CompanyBrands,
  CompanyCitiesProducts,
  CompanySummary,
  CompanyInflow,
  CompanyManagerSpeed,
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

/** New leads by local day and month, per source. Admin/head only. */
export function useCompanyInflow() {
  return useQuery({
    queryKey: ["company-inflow"],
    queryFn: () => api.get<CompanyInflow>("/company/inflow"),
    staleTime: 60 * 1000,
  });
}

/** Handling speed per manager, today and this week. Admin/head only. */
export function useCompanyManagerSpeed() {
  return useQuery({
    queryKey: ["company-manager-speed"],
    queryFn: () => api.get<CompanyManagerSpeed>("/company/manager-speed"),
    staleTime: 60 * 1000,
  });
}

/** Active leads per brand across the workspace. Admin/head only. */
export function useCompanyBrands() {
  return useQuery({
    queryKey: ["company-brands"],
    queryFn: () => api.get<CompanyBrands>("/company/brands"),
    staleTime: 60 * 1000,
  });
}

/** The whole lead base by city and by product. Admin/head only. */
export function useCompanyCitiesProducts() {
  return useQuery({
    queryKey: ["company-cities-products"],
    queryFn: () => api.get<CompanyCitiesProducts>("/company/cities-products"),
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
