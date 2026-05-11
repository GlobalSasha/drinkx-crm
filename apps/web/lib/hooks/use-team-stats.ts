// Team stats hooks — Sprint 3.4 G3.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  ManagerStatsOut,
  TeamPeriod,
  TeamStatsOut,
} from "@/lib/types";

/** GET /api/team/stats — all managers. Admin/head only at the backend. */
export function useTeamStats(period: TeamPeriod) {
  return useQuery<TeamStatsOut>({
    queryKey: ["team-stats", period],
    queryFn: () => api.get<TeamStatsOut>(`/team/stats?period=${period}`),
    staleTime: 30_000,
  });
}

/** GET /api/team/stats/{user_id} — one manager + daily breakdown. */
export function useManagerStats(userId: string | null, period: TeamPeriod) {
  return useQuery<ManagerStatsOut>({
    queryKey: ["manager-stats", userId, period],
    queryFn: () =>
      api.get<ManagerStatsOut>(`/team/stats/${userId}?period=${period}`),
    enabled: !!userId,
    staleTime: 30_000,
  });
}
