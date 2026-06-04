"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { StageDwellStat } from "@/lib/types";

/**
 * «Где застревают сделки» — per active stage dwell stats (median/p90 days +
 * stuck-now count), bottlenecks first (`GET /leads/stage-dwell`). Powers the
 * stage-speed table on the forecast page.
 */
export function useStageDwell() {
  return useQuery<StageDwellStat[]>({
    queryKey: ["stage-dwell"],
    queryFn: () => api.get<StageDwellStat[]>("/leads/stage-dwell"),
    staleTime: 60_000,
  });
}
