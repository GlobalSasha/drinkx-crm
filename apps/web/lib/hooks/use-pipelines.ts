// Hook to fetch pipeline + stages.
// The backend doesn't yet expose GET /pipelines, so we infer stages
// from DEFAULT_STAGES hardcoded to match the seed data.
// When the backend exposes a pipelines endpoint this can be replaced.

import { useQuery } from "@tanstack/react-query";
import type { Stage, Pipeline } from "@/lib/types";

// Mirrors apps/api/app/pipelines/models.py DEFAULT_STAGES
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

// Fallback pipeline used when backend has no /pipelines endpoint yet.
// Stage IDs are derived from the first lead's stage_id on load — until that
// happens we show named columns and map by name.
const PLACEHOLDER_PIPELINE_ID = "default";

function buildFallbackStages(): Stage[] {
  return DEFAULT_STAGES.map((s, i) => ({
    ...s,
    id: `fallback-stage-${i}`,
    pipeline_id: PLACEHOLDER_PIPELINE_ID,
  }));
}

export function usePipelines() {
  return useQuery<Pipeline[]>({
    queryKey: ["pipelines"],
    queryFn: async () => {
      // Return a synthetic pipeline until the backend exposes GET /pipelines.
      const stages = buildFallbackStages();
      const pipeline: Pipeline = {
        id: PLACEHOLDER_PIPELINE_ID,
        workspace_id: "",
        name: "Новые клиенты",
        type: "sales",
        is_default: true,
        position: 0,
        stages,
      };
      return [pipeline];
    },
    staleTime: Infinity, // static data
  });
}
