"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { DailyPlan, DailyPlanItem, RegenerateResponse } from "@/lib/types";

export function useTodayPlan() {
  return useQuery({
    queryKey: ["daily-plan", "today"],
    queryFn: () => api.get<DailyPlan | null>("/me/today"),
    refetchInterval: (q) => {
      const data = q.state.data as DailyPlan | null | undefined;
      return data?.status === "generating" ? 2000 : false;
    },
  });
}

export function useRegenerate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planDate: string) =>
      api.post<RegenerateResponse>(`/daily-plans/${planDate}/regenerate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}

export function useCompletePlanItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) =>
      api.post<DailyPlanItem>(`/daily-plans/items/${itemId}/complete`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["daily-plan", "today"] });
    },
  });
}
