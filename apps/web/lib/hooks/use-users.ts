// Hooks for the Settings «Команда» section — Sprint 2.4 G1.
//
// Read access (list users + invites) is open to all roles; write
// actions (invite, role change) are admin-only at the backend, the
// frontend section component just hides the buttons for non-admins.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import type {
  UserInviteIn,
  UserInviteOut,
  UserListItemOut,
  UserListOut,
  UserRoleUpdateIn,
} from "@/lib/types";

/** GET /api/users — workspace user list. Available to all roles. */
export function useUsers() {
  return useQuery<UserListOut>({
    queryKey: ["users"],
    queryFn: () => api.get<UserListOut>("/users"),
    staleTime: 60_000,
  });
}

/** GET /api/users/invites — workspace invite list. */
export function useUserInvites() {
  return useQuery<UserInviteOut[]>({
    queryKey: ["user-invites"],
    queryFn: () => api.get<UserInviteOut[]>("/users/invites"),
    staleTime: 60_000,
  });
}

/**
 * POST /api/users/invite — admin only.
 *
 * Errors flow through TanStack's standard onError. Caller reads
 * `error.body.detail` to detect the structured 502 shape
 * (`code: invite_send_failed`) and renders a «retry later» state.
 */
export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation<UserInviteOut, ApiError, UserInviteIn>({
    mutationFn: (body) => api.post<UserInviteOut>("/users/invite", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user-invites"] });
    },
  });
}

/**
 * PATCH /api/users/{id}/role — admin only.
 *
 * Backend's structured 409 (`code: last_admin`) is the contract we
 * respect — caller checks `error.body.detail.code === "last_admin"`
 * to render the «promote someone else first» modal. Same pattern
 * as Sprint 2.3 PipelineHasLeads / PipelineIsDefault.
 */
/**
 * DELETE /api/users/{id} — admin only. Returns 204; the deleted user's
 * active leads go back to the pool.
 *
 * Structured 400 detail shapes the caller checks:
 *   - { code: "cannot_delete_self" }
 *   - { code: "last_admin" }
 */
export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) => api.delete<void>(`/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["team-stats"] });
      qc.invalidateQueries({ queryKey: ["leads-pool"] });
    },
  });
}

export function useChangeUserRole() {
  const qc = useQueryClient();
  return useMutation<
    UserListItemOut,
    ApiError,
    { id: string; body: UserRoleUpdateIn }
  >({
    mutationFn: ({ id, body }) =>
      api.patch<UserListItemOut>(`/users/${id}/role`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      // Also bump ['me'] in case the admin demoted themselves —
      // the next page load needs to see the new role.
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
