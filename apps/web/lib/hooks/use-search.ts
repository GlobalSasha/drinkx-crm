"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { SearchResponse } from "@/lib/types";

/** Debounce a string by `delayMs`. Used by the Cmd+K overlay so we
 *  don't fire `/api/search` on every keystroke. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

export function useGlobalSearch(query: string, limit = 20) {
  const debounced = useDebouncedValue(query, 200);
  const trimmed = debounced.trim();
  return useQuery<SearchResponse>({
    queryKey: ["search", trimmed, limit],
    queryFn: () =>
      api.get<SearchResponse>(
        `/search?q=${encodeURIComponent(trimmed)}&limit=${limit}`,
      ),
    enabled: trimmed.length > 0,
    staleTime: 30_000,
  });
}

/** Lightweight company-only autocomplete — used by CreateLeadModal.
 *  Returns only `type === 'company'` rows. */
export function useCompanyAutocomplete(query: string, limit = 10) {
  const result = useGlobalSearch(query, limit);
  const items = (result.data?.items ?? []).filter((it) => it.type === "company");
  return { ...result, items };
}
