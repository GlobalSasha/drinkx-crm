// Hook for Settings → Каналы — Sprint 2.4 G2.
//
// Read-only summary of Gmail (per current user) + SMTP (workspace
// config). Both data sources already exist; this just resolves
// them into a single payload for the ChannelsSection card layout.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ChannelsStatusOut } from "@/lib/types";

export function useChannelsStatus() {
  return useQuery<ChannelsStatusOut>({
    queryKey: ["channels-status"],
    queryFn: () => api.get<ChannelsStatusOut>("/settings/channels"),
    // Re-poll on focus — e.g., after the user comes back from the
    // Gmail OAuth tab, the connection status should update without
    // a manual refresh.
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}
