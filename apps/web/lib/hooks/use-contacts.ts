import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type { ContactOut, ContactCreate, ContactUpdate } from "@/lib/types";

export function useContacts(leadId: string) {
  return useQuery<ContactOut[]>({
    queryKey: ["contacts", leadId],
    queryFn: () => api.get<ContactOut[]>(`/leads/${leadId}/contacts`),
    enabled: !!leadId,
  });
}

export function useCreateContact(leadId: string) {
  const qc = useQueryClient();
  return useMutation<ContactOut, ApiError, ContactCreate>({
    mutationFn: (body) => api.post<ContactOut>(`/leads/${leadId}/contacts`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts", leadId] });
    },
  });
}

export function useUpdateContact(leadId: string, contactId: string) {
  const qc = useQueryClient();
  return useMutation<ContactOut, ApiError, ContactUpdate>({
    mutationFn: (body) =>
      api.patch<ContactOut>(`/leads/${leadId}/contacts/${contactId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts", leadId] });
    },
  });
}

export function useDeleteContact(leadId: string) {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (contactId) =>
      api.delete<void>(`/leads/${leadId}/contacts/${contactId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts", leadId] });
    },
  });
}
