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
import { Priority } from "@/lib/types";

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

export function usePoolLeads(
  filters: { city?: string; segment?: string; page_size?: number } = {},
) {
  const p = new URLSearchParams();
  if (filters.city) p.set("city", filters.city);
  if (filters.segment) p.set("segment", filters.segment);
  p.set("page_size", String(filters.page_size ?? 200));
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

// ---- Today screen ----

const PRIORITY_ORDER: Record<Priority, number> = { A: 0, B: 1, C: 2, D: 3 };

/**
 * Fetches all leads (no assigned_to filter — auth integration is Phase 2).
 * Sorts client-side: next_action_at ASC NULLS LAST, then priority A>B>C>D,
 * then created_at DESC.
 *
 * NOTE: We intentionally omit the assigned_to filter here. Once /auth/me lands
 * in a future sprint, pass `assigned_to=currentUser.id`. For now we show all
 * leads so the screen is usable in dev/demo mode.
 */
export function useTodayLeads() {
  const query = useQuery<LeadListOut>({
    queryKey: ["leads", { page_size: 200 }],
    queryFn: () => api.get<LeadListOut>("/leads?page_size=200"),
  });

  const sorted = [...(query.data?.items ?? [])].sort((a, b) => {
    const aDate = a.next_action_at ? new Date(a.next_action_at).getTime() : Infinity;
    const bDate = b.next_action_at ? new Date(b.next_action_at).getTime() : Infinity;
    if (aDate !== bDate) return aDate - bDate;

    const aPri = a.priority ? PRIORITY_ORDER[a.priority] : 99;
    const bPri = b.priority ? PRIORITY_ORDER[b.priority] : 99;
    if (aPri !== bPri) return aPri - bPri;

    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  return { ...query, sorted };
}

// ---- Claim lead ----

/**
 * POST /leads/{id}/claim — move a pool lead into the current user's pipeline.
 * Optimistically removes the lead from the leads-pool cache immediately.
 * On 409 (race): reverts + emits error for caller to show a toast.
 */
export function useClaimLead() {
  const qc = useQueryClient();

  return useMutation<LeadOut, ApiError, string>({
    mutationFn: (leadId) => api.post<LeadOut>(`/leads/${leadId}/claim`),

    onMutate: async (leadId) => {
      await qc.cancelQueries({ queryKey: ["leads-pool"] });

      // Snapshot all pool cache entries for rollback.
      const snapshots: [unknown[], LeadListOut | undefined][] = [];
      qc.getQueriesData<LeadListOut>({ queryKey: ["leads-pool"] }).forEach(
        ([key, data]) => {
          snapshots.push([key as unknown[], data]);
          if (!data) return;
          qc.setQueryData<LeadListOut>(key as unknown[], {
            ...data,
            items: data.items.filter((l) => l.id !== leadId),
            total: Math.max(0, data.total - 1),
          });
        }
      );
      return { snapshots };
    },

    onError: (_err, _leadId, context) => {
      const ctx = context as { snapshots: [unknown[], LeadListOut | undefined][] } | undefined;
      ctx?.snapshots.forEach(([key, data]) => {
        qc.setQueryData(key as unknown[], data);
      });
    },

    onSuccess: () => {
      // Newly claimed lead is now in the user's pipeline.
      qc.invalidateQueries({ queryKey: ["leads"] });
    },

    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });
}
