import {
  keepPreviousData,
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import {
  poolQueryParams,
  poolScopeParams,
  type PoolFilterState,
} from "@/lib/leads-pool-filters";
import type {
  LeadListOut,
  LeadOut,
  PoolFacets,
  LeadCreate,
  SprintCreateIn,
  SprintCreateOut,
  MoveStageIn,
  LeadAssignIn,
  LeadAssignOut,
} from "@/lib/types";
import { Priority } from "@/lib/types";

export interface LeadFilters {
  stage_id?: string;
  // Sprint 2.3 G2: scope the board to one voronka. /today and
  // /leads-pool intentionally don't pass this — they aggregate across
  // all of the user's pipelines.
  pipeline_id?: string;
  segment?: string;
  city?: string;
  priority?: string;
  deal_type?: string;
  q?: string;
  // Sprint 3.6 G4 — filter by landing-form source.
  form_id?: string;
  // Manager workload: admin/head can scope the board to one manager
  // (assigned_to) or the whole workspace (all_assignees).
  assigned_to?: string;
  all_assignees?: boolean;
  // Opt-in for whole-workspace text search (the message-to-lead picker).
  // The kanban search box deliberately does NOT set this, so a regular
  // user's q stays scoped to their own leads.
  workspace_search?: boolean;
  page?: number;
  page_size?: number;
}

function buildQuery(filters: LeadFilters): string {
  const p = new URLSearchParams();
  if (filters.stage_id) p.set("stage_id", filters.stage_id);
  if (filters.pipeline_id) p.set("pipeline_id", filters.pipeline_id);
  if (filters.segment) p.set("segment", filters.segment);
  if (filters.city) p.set("city", filters.city);
  if (filters.priority) p.set("priority", filters.priority);
  if (filters.deal_type) p.set("deal_type", filters.deal_type);
  if (filters.q) p.set("q", filters.q);
  if (filters.form_id) p.set("form_id", filters.form_id);
  if (filters.assigned_to) p.set("assigned_to", filters.assigned_to);
  if (filters.all_assignees) p.set("all_assignees", "true");
  if (filters.workspace_search) p.set("workspace_search", "true");
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

/** Сколько карточек базы приходит за один запрос. */
export const POOL_PAGE_SIZE = 50;

/**
 * GET /leads/pool — одна страница базы лидов.
 *
 * Весь отбор на сервере. До G6 сюда уходили только форма и needs_review,
 * фронтенд просил 500 строк и решал принадлежность к выборке у себя —
 * карточка за этой границей не находилась ни поиском, ни фильтром
 * (аудит G6). Никакого `page_size: 500` здесь больше нет и быть не должно.
 */
export function usePoolLeads(
  filters: PoolFilterState,
  page: number,
  options: { pageSize?: number } = {},
) {
  const pageSize = options.pageSize ?? POOL_PAGE_SIZE;
  const params = poolQueryParams(filters);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const qs = params.toString();

  return useQuery<LeadListOut>({
    // Ключ включает фильтры и страницу: смена любого условия — другой
    // запрос, а не пересортировка уже загруженного.
    queryKey: ["leads-pool", qs],
    queryFn: () => api.get<LeadListOut>(`/leads/pool?${qs}`),
    placeholderData: keepPreviousData,
  });
}

/**
 * GET /leads/pool/facets — значения фильтров и их размеры.
 *
 * Отдельным запросом: числа зависят только от области пула (форма и
 * needs_review) и не меняются при листании и выборе фасетов, поэтому
 * переход на следующую страницу их не перезапрашивает.
 */
export function usePoolFacets(filters: PoolFilterState) {
  const qs = poolScopeParams(filters).toString();
  const path = qs ? `/leads/pool/facets?${qs}` : "/leads/pool/facets";
  return useQuery<PoolFacets>({
    queryKey: ["leads-pool-facets", qs],
    queryFn: () => api.get<PoolFacets>(path),
    staleTime: 60_000,
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

export function useTransferLead() {
  const qc = useQueryClient();
  return useMutation<
    LeadOut,
    ApiError,
    { leadId: string; to_user_id: string; comment?: string | null }
  >({
    mutationFn: ({ leadId, to_user_id, comment }) =>
      api.post<LeadOut>(`/leads/${leadId}/transfer`, {
        to_user_id,
        comment: comment ?? null,
      }),
    onSuccess: (_lead, vars) => {
      qc.invalidateQueries({ queryKey: ["lead", vars.leadId] });
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

    onError: (_err, _leadId, _context) => {
      // Plan 026: do NOT restore a whole pre-mutation snapshot — with two
      // overlapping claims, restoring a stale snapshot can resurrect a lead
      // the other claim already removed. Just invalidate and let the refetch
      // (onSettled) reconcile to the true server state.
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
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

/**
 * POST /leads/assign — руководитель/админ выдаёт карточки из базы менеджеру.
 * Без optimistic update — результат зависит от того, что реально осталось
 * в пуле на сервере (см. `only_pool`).
 */
export function useAssignLeads() {
  const qc = useQueryClient();
  return useMutation<LeadAssignOut, ApiError, LeadAssignIn>({
    mutationFn: (body) => api.post<LeadAssignOut>("/leads/assign", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["team-stats"] });
    },
  });
}

/**
 * POST /leads/{id}/unclaim — release the lead back to the workspace pool.
 * Backend rejects with 403 unless the current user is the owner.
 */
export function useUnclaimLead() {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, string>({
    mutationFn: (leadId) => api.post<LeadOut>(`/leads/${leadId}/unclaim`),
    onSuccess: (_data, leadId) => {
      qc.invalidateQueries({ queryKey: ["leads"] });
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
    },
  });
}
