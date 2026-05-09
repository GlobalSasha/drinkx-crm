// Hooks for Settings → AI section — Sprint 2.4 G3.
//
// Admin-only. The AI card surfaces the workspace's daily budget cap
// + preferred LLM provider + live spend gauge. PATCH writes back
// into workspace.settings_json["ai"] (no migration — JSON column
// has existed since Sprint 1.1).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { AISettingsOut, AISettingsUpdateIn } from "@/lib/types";

export function useAISettings() {
  return useQuery<AISettingsOut>({
    queryKey: ["settings-ai"],
    queryFn: () => api.get<AISettingsOut>("/settings/ai"),
    // Spend gauge wants to update on focus — coming back from another
    // tab where enrichment ran shouldn't show stale 0%.
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useUpdateAISettings() {
  const qc = useQueryClient();
  return useMutation<AISettingsOut, ApiError, AISettingsUpdateIn>({
    mutationFn: (body) =>
      api.patch<AISettingsOut>("/settings/ai", body),
    onSuccess: (next) => {
      qc.setQueryData(["settings-ai"], next);
    },
  });
}
