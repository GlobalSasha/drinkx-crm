"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { MeOut, UiPrefsPatch } from "@/lib/types";

/**
 * PATCH /auth/me/ui-prefs — partial update of the current user's
 * appearance preferences. The backend merges over stored values and
 * returns the full `MeOut`; we drop it into the `me` query cache so
 * any consumer (including `<ThemeApplier/>`) re-renders with the new
 * settings immediately.
 */
export function useUpdateUiPrefs() {
  const qc = useQueryClient();
  return useMutation<MeOut, ApiError, UiPrefsPatch>({
    mutationFn: (patch) => api.patch<MeOut>("/auth/me/ui-prefs", patch),
    onSuccess: (me) => {
      qc.setQueryData<MeOut>(["me"], me);
    },
  });
}
