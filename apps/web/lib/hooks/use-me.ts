"use client";

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { MeOut } from "@/lib/types";

/**
 * Fetch the current user from the backend (`/auth/me`).
 * Includes role, workspace, onboarding state, etc. — info the Supabase
 * JWT alone doesn't carry.
 *
 * staleTime is generous because role rarely changes mid-session and we
 * don't want a refetch on every page mount.
 */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<MeOut>("/auth/me"),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: (failureCount, error) =>
      !(error instanceof ApiError && error.status === 403) && failureCount < 2,
  });
}
