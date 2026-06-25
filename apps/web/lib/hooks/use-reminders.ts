"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";

export interface ReminderOut {
  id: string;
  text: string;
  created_at: string;
}

export function useReminders() {
  return useQuery<ReminderOut[]>({
    queryKey: ["reminders"],
    queryFn: () => api.get<ReminderOut[]>("/api/reminders"),
    staleTime: 30_000,
  });
}

export function useCreateReminder() {
  const qc = useQueryClient();
  return useMutation<ReminderOut, ApiError, string>({
    mutationFn: (text) => api.post<ReminderOut>("/api/reminders", { text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
}

export function useUpdateReminder() {
  const qc = useQueryClient();
  return useMutation<ReminderOut, ApiError, { id: string; text: string }>({
    mutationFn: ({ id, text }) =>
      api.patch<ReminderOut>(`/api/reminders/${id}`, { text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
}

export function useDeleteReminder() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/api/reminders/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
}
