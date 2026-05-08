// Hooks against the real GET /api/pipelines surface — Sprint 2.3 G2.
//
// Until G1 the frontend rendered a hardcoded fallback pipeline; now
// that the backend exposes admin CRUD we read the workspace's actual
// pipelines + their stages. The DEFAULT_STAGES export is kept around
// purely as a seed for the upcoming Settings PipelineEditor (G3) — it
// is no longer used by the live UI.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  Pipeline,
  PipelineCreateIn,
  PipelineUpdateIn,
  Stage,
} from "@/lib/types";

// Mirrors apps/api/app/pipelines/models.py DEFAULT_STAGES.
// Used by the Settings PipelineEditor (G3) as the «start from the
// 11-stage B2B template» seed. Not consumed by the live /pipeline view.
export const DEFAULT_STAGES: Omit<Stage, "id" | "pipeline_id">[] = [
  { name: "Новый контакт",      position: 0,  color: "#a1a1a6", rot_days: 3,  probability: 5,   is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Квалификация",       position: 1,  color: "#0a84ff", rot_days: 5,  probability: 15,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Discovery",          position: 2,  color: "#5e5ce6", rot_days: 7,  probability: 25,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Solution Fit",       position: 3,  color: "#bf5af2", rot_days: 7,  probability: 40,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Business Case / КП", position: 4,  color: "#ff9f0a", rot_days: 5,  probability: 50,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Multi-stakeholder",  position: 5,  color: "#ff6b00", rot_days: 7,  probability: 60,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Договор / пилот",    position: 6,  color: "#ff3b30", rot_days: 5,  probability: 75,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Производство",       position: 7,  color: "#ff2d55", rot_days: 10, probability: 85,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Пилот",              position: 8,  color: "#34c759", rot_days: 14, probability: 90,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Scale / серия",      position: 9,  color: "#30d158", rot_days: 14, probability: 95,  is_won: false, is_lost: false, gate_criteria_json: [] },
  { name: "Закрыто (won)",      position: 10, color: "#32d74b", rot_days: 0,  probability: 100, is_won: true,  is_lost: false, gate_criteria_json: [] },
  { name: "Закрыто (lost)",     position: 11, color: "#ff3b30", rot_days: 0,  probability: 0,   is_won: false, is_lost: true,  gate_criteria_json: [] },
];

export function usePipelines() {
  return useQuery<Pipeline[]>({
    queryKey: ["pipelines"],
    queryFn: () => api.get<Pipeline[]>("/pipelines"),
    // Pipelines change once a quarter, not once a request. 60s is
    // long enough to dedupe the obvious bursts during board reloads
    // but short enough that a settings edit shows up on a tab switch
    // without a hard refresh.
    staleTime: 60_000,
  });
}

/**
 * POST /api/pipelines/{id}/set-default — flips the workspace default.
 * Invalidates ['pipelines'] AND ['me'] on success: the dropdown's
 * «по умолчанию» badge moves to the new default and the next cold-
 * load picks it up.
 */
export function useSetDefaultPipeline() {
  const qc = useQueryClient();
  return useMutation<Pipeline, ApiError, string>({
    mutationFn: (pipelineId) =>
      api.post<Pipeline>(`/pipelines/${pipelineId}/set-default`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

/** GET /api/pipelines/{id} — workspace-scoped detail with stages. */
export function usePipeline(id: string | null) {
  return useQuery<Pipeline>({
    queryKey: ["pipeline", id],
    queryFn: () => api.get<Pipeline>(`/pipelines/${id}`),
    enabled: !!id,
    staleTime: 60_000,
  });
}

/** POST /api/pipelines — admin/head only at the backend. */
export function useCreatePipeline() {
  const qc = useQueryClient();
  return useMutation<Pipeline, ApiError, PipelineCreateIn>({
    mutationFn: (body) => api.post<Pipeline>("/pipelines", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}

/** PATCH /api/pipelines/{id} — rename + optional full-replace of stages. */
export function useUpdatePipeline() {
  const qc = useQueryClient();
  return useMutation<
    Pipeline,
    ApiError,
    { id: string; body: PipelineUpdateIn }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<Pipeline>(`/pipelines/${id}`, body),
    onSuccess: (_pipeline, vars) => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      qc.invalidateQueries({ queryKey: ["pipeline", vars.id] });
      // The board may be looking at this pipeline — invalidate leads
      // too so a stage rename reflects without a hard refresh.
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}

/**
 * DELETE /api/pipelines/{id}.
 *
 * The backend's structured 409 (`pipeline_has_leads` /
 * `pipeline_is_default`) is the contract we respect — the caller
 * checks `error.body` to render the right friendly modal. We still
 * surface the rejection through the standard mutation error path
 * (TanStack Query's `onError` / `error`) so callers can `mutate`
 * with `{ onError }` like every other mutation in the codebase.
 *
 * `mutationFn` returns `null` on success (DELETE → 204 No Content;
 * the api-client returns `null` for empty bodies).
 */
export function useDeletePipeline() {
  const qc = useQueryClient();
  return useMutation<null, ApiError, string>({
    mutationFn: (id) => api.delete<null>(`/pipelines/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
    },
  });
}
