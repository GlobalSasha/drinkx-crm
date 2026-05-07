"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { AuditLogPageOut } from "@/lib/types";

interface UseAuditLogParams {
  entity_type?: string;
  entity_id?: string;
  page: number;
}

/**
 * Read-side audit log query. Historical data — no polling, generous
 * staleTime. The backend caps page_size at 200; we always request 50
 * (matches the page-size baked into the page UI).
 */
export function useAuditLog(params: UseAuditLogParams) {
  const { entity_type, entity_id, page } = params;
  const qs = new URLSearchParams();
  if (entity_type) qs.set("entity_type", entity_type);
  if (entity_id) qs.set("entity_id", entity_id);
  qs.set("page", String(page));
  qs.set("page_size", "50");

  const path = `/audit?${qs.toString()}`;

  return useQuery({
    queryKey: ["audit", { entity_type, entity_id, page }],
    queryFn: () => api.get<AuditLogPageOut>(path),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}
