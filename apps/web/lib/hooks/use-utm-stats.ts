"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { UtmSourceStat } from "@/lib/types";

/**
 * «Каналы привлечения» — leads grouped by UTM source with won-deal count
 * and revenue (`GET /leads/utm-stats`). Powers the channel table on the
 * forecast page.
 */
export function useUtmStats() {
  return useQuery<UtmSourceStat[]>({
    queryKey: ["utm-stats"],
    queryFn: () => api.get<UtmSourceStat[]>("/leads/utm-stats"),
    staleTime: 60_000,
  });
}
