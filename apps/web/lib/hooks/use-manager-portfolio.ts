"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ManagerPortfolio } from "@/lib/types";

/**
 * A manager's active-deal portfolio — KPIs + segment/stage/priority breakdowns
 * + top deals (`GET /team/{user_id}/portfolio`). Admin/head only.
 */
export function useManagerPortfolio(userId: string | null) {
  return useQuery<ManagerPortfolio>({
    queryKey: ["manager-portfolio", userId],
    queryFn: () => api.get<ManagerPortfolio>(`/team/${userId}/portfolio`),
    enabled: !!userId,
    staleTime: 60_000,
  });
}
