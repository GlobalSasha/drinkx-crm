import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  LeadListOut,
  LeadOut,
  LeadCreate,
  SprintCreateIn,
  SprintCreateOut,
  MoveStageIn,
} from "@/lib/types";

export interface LeadFilters {
  stage_id?: string;
  segment?: string;
  city?: string;
  priority?: string;
  deal_type?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

function buildQuery(filters: LeadFilters): string {
  const p = new URLSearchParams();
  if (filters.stage_id) p.set("stage_id", filters.stage_id);
  if (filters.segment) p.set("segment", filters.segment);
  if (filters.city) p.set("city", filters.city);
  if (filters.priority) p.set("priority", filters.priority);
  if (filters.deal_type) p.set("deal_type", filters.deal_type);
  if (filters.q) p.set("q", filters.q);
  if (filters.page) p.set("page", String(filters.page));
  p.set("page_size", String(filters.page_size ?? 200));
  const qs = p.toString();
  return qs ? `/leads?${qs}` : "/leads";
}

export function useLeads(filters: LeadFilters = {}) {
  return useQuery<LeadListOut>({
    queryKey: ["leads", filters],
    queryFn: () => api.get<LeadListOut>(buildQuery(filters)),
  });
}

export function usePoolLeads(filters: { city?: string; segment?: string } = {}) {
  const p = new URLSearchParams();
  if (filters.city) p.set("city", filters.city);
  if (filters.segment) p.set("segment", filters.segment);
  p.set("page_size", "200");
  const qs = p.toString();
  const path = qs ? `/leads/pool?${qs}` : "/leads/pool";

  return useQuery<LeadListOut>({
    queryKey: ["leads-pool", filters],
    queryFn: () => api.get<LeadListOut>(path),
  });
}

export function useCreateLead() {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, LeadCreate>({
    mutationFn: (body) => api.post<LeadOut>("/leads", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useMoveStage() {
  const qc = useQueryClient();

  return useMutation<
    LeadOut,
    ApiError,
    { leadId: string; body: MoveStageIn; previousLead?: LeadOut }
  >({
    mutationFn: ({ leadId, body }) =>
      api.post<LeadOut>(`/leads/${leadId}/move-stage`, body),
    onMutate: async ({ leadId, body }) => {
      // Cancel in-flight refetches to avoid race conditions.
      await qc.cancelQueries({ queryKey: ["leads"] });

      // Snapshot all leads query caches for rollback.
      const snapshots: [unknown[], LeadListOut | undefined][] = [];
      qc.getQueriesData<LeadListOut>({ queryKey: ["leads"] }).forEach(
        ([key, data]) => {
          snapshots.push([key as unknown[], data]);
          if (!data) return;
          qc.setQueryData<LeadListOut>(key as unknown[], {
            ...data,
            items: data.items.map((l) =>
              l.id === leadId ? { ...l, stage_id: body.stage_id } : l
            ),
          });
        }
      );
      return { snapshots };
    },
    onError: (_err, _vars, context) => {
      const ctx = context as { snapshots: [unknown[], LeadListOut | undefined][] } | undefined;
      ctx?.snapshots.forEach(([key, data]) => {
        qc.setQueryData(key as unknown[], data);
      });
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

export function useCreateSprint() {
  const qc = useQueryClient();
  return useMutation<SprintCreateOut, ApiError, SprintCreateIn>({
    mutationFn: (body) => api.post<SprintCreateOut>("/leads/sprint", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });
}
