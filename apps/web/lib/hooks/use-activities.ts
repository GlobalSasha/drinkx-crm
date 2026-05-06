import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { ActivityOut, ActivityCreate, ActivityListOut } from "@/lib/types";

export function useActivities(leadId: string, type?: string) {
  return useInfiniteQuery<ActivityListOut>({
    queryKey: ["activities", leadId, type],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => {
      const cursor = pageParam as string | undefined;
      let url = `/leads/${leadId}/activities?limit=20`;
      if (type) url += `&type=${type}`;
      if (cursor) url += `&cursor=${cursor}`;
      return api.get<ActivityListOut>(url);
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!leadId,
  });
}

export function useCreateActivity(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ActivityOut, ApiError, ActivityCreate>({
    mutationFn: (body) =>
      api.post<ActivityOut>(`/leads/${leadId}/activities`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activities", leadId] });
    },
  });
}

export function useCompleteTask(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ActivityOut, ApiError, string>({
    mutationFn: (activityId) =>
      api.post<ActivityOut>(
        `/leads/${leadId}/activities/${activityId}/complete-task`
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["activities", leadId] });
    },
  });
}
