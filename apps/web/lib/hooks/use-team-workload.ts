"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Workload } from "@/lib/types";

/** GET /api/team/workload — manager × stage load. Admin/head only at the backend. */
export function useTeamWorkload() {
  return useQuery<Workload>({
    queryKey: ["team-workload"],
    queryFn: () => api.get<Workload>("/team/workload"),
    staleTime: 60_000,
  });
}
