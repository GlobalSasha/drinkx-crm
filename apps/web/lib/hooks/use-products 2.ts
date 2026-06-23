"use client";

// Quote catalog hooks (Phase 1). Backend: /api/products (list open to all
// roles; create/update/delete/seed gated admin/head server-side).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { ProductOut } from "@/lib/types";

const KEY = ["products", "list"] as const;

export function useProducts() {
  return useQuery<ProductOut[]>({
    queryKey: KEY,
    queryFn: () => api.get<ProductOut[]>("/api/products"),
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; category: string; unit_price: number }) =>
      api.post<ProductOut>("/api/products", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: string } & Partial<ProductOut>) =>
      api.patch<ProductOut>(`/api/products/${id}`, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeactivateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<ProductOut>(`/api/products/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useSeedStarterCatalog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<ProductOut[]>("/api/products/seed-starter", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
