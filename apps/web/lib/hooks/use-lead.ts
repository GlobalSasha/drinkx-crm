import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { LeadOut, LeadUpdateExtended } from "@/lib/types";

export function useLead(id: string) {
  return useQuery<LeadOut>({
    queryKey: ["lead", id],
    queryFn: () => api.get<LeadOut>(`/leads/${id}`),
    enabled: !!id,
  });
}

export function useUpdateLead(id: string) {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, LeadUpdateExtended>({
    mutationFn: (body) => api.patch<LeadOut>(`/leads/${id}`, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: ["lead", id] });
      const prev = qc.getQueryData<LeadOut>(["lead", id]);
      if (prev) {
        qc.setQueryData<LeadOut>(["lead", id], { ...prev, ...body });
      }
      return { prev };
    },
    onError: (_err, _vars, context) => {
      const ctx = context as { prev?: LeadOut } | undefined;
      if (ctx?.prev) qc.setQueryData(["lead", id], ctx.prev);
    },
    onSuccess: (data) => {
      qc.setQueryData(["lead", id], data);
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
