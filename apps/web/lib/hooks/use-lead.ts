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

export function useDeleteLead(id: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => api.delete<void>(`/leads/${id}`),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["lead", id] });
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}


/**
 * Pin one Contact as «основной ЛПР» on the lead. Pass `null` to unpin.
 * Setting a new primary automatically replaces the previous — the
 * backend column is a single FK, so we don't have to clear the old
 * one client-side.
 *
 * Optimistic: writes `primary_contact_id` into the cached LeadOut
 * immediately so the star in the contacts tab flips without a
 * round-trip. The server returns the full `LeadOut` with the joined
 * `primary_contact_name`, which we then drop into the cache.
 */
export function useSetPrimaryContact(leadId: string) {
  const qc = useQueryClient();
  return useMutation<LeadOut, ApiError, string | null>({
    mutationFn: (contactId) =>
      api.patch<LeadOut>(`/leads/${leadId}/primary-contact`, {
        contact_id: contactId,
      }),
    onMutate: async (contactId) => {
      await qc.cancelQueries({ queryKey: ["lead", leadId] });
      const prev = qc.getQueryData<LeadOut>(["lead", leadId]);
      if (prev) {
        qc.setQueryData<LeadOut>(["lead", leadId], {
          ...prev,
          primary_contact_id: contactId,
        });
      }
      return { prev };
    },
    onError: (_err, _vars, context) => {
      const ctx = context as { prev?: LeadOut } | undefined;
      if (ctx?.prev) qc.setQueryData(["lead", leadId], ctx.prev);
    },
    onSuccess: (lead) => {
      qc.setQueryData(["lead", leadId], lead);
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
