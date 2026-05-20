"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { LlmCosts } from "@/lib/types";

export type CostPeriod = "this_month" | "last_month" | "all";

export function useLlmCosts(period: CostPeriod) {
  return useQuery({
    queryKey: ["llm-costs", period],
    queryFn: () => api.get<LlmCosts>(`/admin/llm-costs?period=${period}`),
    staleTime: 60_000,
  });
}
