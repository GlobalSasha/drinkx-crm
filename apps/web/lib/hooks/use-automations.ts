// Hooks for /automations — Sprint 2.5 G1.
//
// Read-open to all roles (managers may want to see what's configured).
// Writes are admin/head-only at the backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  AutomationCreate,
  AutomationOut,
  AutomationRunOut,
  AutomationStepRunOut,
  AutomationUpdate,
} from "@/lib/types";

const KEY = ["automations"] as const;

export function useAutomations() {
  return useQuery<AutomationOut[]>({
    queryKey: KEY,
    queryFn: () => api.get<AutomationOut[]>("/automations"),
    staleTime: 60_000,
  });
}

export function useAutomationRuns(automationId: string | null) {
  return useQuery<AutomationRunOut[]>({
    queryKey: ["automation-runs", automationId],
    queryFn: () =>
      api.get<AutomationRunOut[]>(
        `/automations/${automationId}/runs?limit=20`,
      ),
    enabled: !!automationId,
    staleTime: 30_000,
  });
}

export function useCreateAutomation() {
  const qc = useQueryClient();
  return useMutation<AutomationOut, ApiError, AutomationCreate>({
    mutationFn: (body) =>
      api.post<AutomationOut>("/automations", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useUpdateAutomation(id: string) {
  const qc = useQueryClient();
  return useMutation<AutomationOut, ApiError, AutomationUpdate>({
    mutationFn: (body) =>
      api.patch<AutomationOut>(`/automations/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useDeleteAutomation() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/automations/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

// Sprint 2.7 G2 — per-step grid for the RunsDrawer.
export function useAutomationStepRuns(runId: string | null) {
  return useQuery<AutomationStepRunOut[]>({
    queryKey: ["automation-step-runs", runId],
    queryFn: () =>
      api.get<AutomationStepRunOut[]>(
        `/automations/runs/${runId}/steps`,
      ),
    enabled: !!runId,
    staleTime: 15_000,
  });
}
