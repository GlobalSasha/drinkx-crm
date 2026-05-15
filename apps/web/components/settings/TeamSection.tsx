"use client";
import Link from "next/link";
// TeamSection — Sprint 2.4 G1.
//
// Renders the workspace's users + pending invites as a single table.
// All roles can read; admin-only sees the «+ Пригласить» CTA, the
// inline role dropdown, and (eventually) the «Удалить» action. Friendly
// modals consume the backend's structured errors:
//   - 502 {code: invite_send_failed}  → «retry later»
//   - 409 {code: last_admin}         → «promote someone else first»
import { useState } from "react";
import { Loader2, Mail, Plus, Shield, Trash2, UserCircle2, X } from "lucide-react";

import { T } from "@/lib/design-system";
import { ApiError } from "@/lib/api-client";
import { relativeTime as relativeTimeBase } from "@/lib/relative-time";
import { useMe } from "@/lib/hooks/use-me";
import {
  useChangeUserRole,
  useDeleteUser,
  useInviteUser,
  useUserInvites,
  useUsers,
} from "@/lib/hooks/use-users";
import type {
  UserInviteIn,
  UserListItemOut,
} from "@/lib/types";

const ROLE_LABEL: Record<string, string> = {
  admin: "Админ",
  head: "Руководитель",
  manager: "Менеджер",
};
const ROLE_OPTIONS: ("admin" | "head" | "manager")[] = ["admin", "head", "manager"];

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  return relativeTimeBase(iso) || "—";
}

export function TeamSection() {
  const meQuery = useMe();
  const usersQuery = useUsers();
  const invitesQuery = useUserInvites();

  const isAdmin = meQuery.data?.role === "admin";
  const isAdminOrHead = isAdmin || meQuery.data?.role === "head";
  const users = usersQuery.data?.items ?? [];
  const invites = invitesQuery.data ?? [];
  // Show pending invites only — accepted ones already have a User row.
  const pendingInvites = invites.filter((i) => !i.accepted_at);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<UserListItemOut | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const del = useDeleteUser();

  function performDelete() {
    if (!deleteTarget) return;
    setDeleteError(null);
    del.mutate(deleteTarget.id, {
      onSuccess: () => {
        setDeleteTarget(null);
      },
      onError: (err: ApiError) => {
        const detail =
          err.body && typeof err.body === "object"
            ? (err.body as { detail?: unknown }).detail
            : null;
        const code =
          detail && typeof detail === "object" && "code" in (detail as object)
            ? (detail as { code: string }).code
            : null;
        if (code === "cannot_delete_self") {
          setDeleteError("Нельзя удалить себя.");
        } else if (code === "last_admin") {
          setDeleteError(
            "Нельзя удалить последнего администратора — сначала повысьте кого-то ещё.",
          );
        } else {
          setDeleteError(
            typeof detail === "string"
              ? detail
              : "Не удалось удалить пользователя.",
          );
        }
      },
    });
  }

  if (usersQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-muted-2" />
      </div>
    );
  }

  if (usersQuery.isError) {
    return (
      <p className="text-sm text-rose py-8 text-center">
        Не удалось загрузить команду. Попробуйте позже.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="type-card-title">Команда</h2>
          <p className="text-xs text-muted-2 mt-0.5">
            Все пользователи общего workspace. Админ может приглашать
            новых членов и менять роли.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isAdminOrHead && (
            <Link
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              href={"/team" as any}
              className={`inline-flex items-center gap-1.5 ${T.mono} uppercase text-muted-2 hover:text-ink transition-colors`}
            >
              Дашборд →
            </Link>
          )}
          {isAdmin && (
            <button
              onClick={() => setInviteOpen(true)}
              className="inline-flex items-center gap-1.5 bg-ink text-white rounded-pill px-4 py-2 text-sm font-semibold hover:bg-ink/90 active:scale-[0.98] transition-all duration-300"
            >
              <Plus size={14} />
              Пригласить
            </button>
          )}
        </div>
      </div>

      {/* Users table */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-canvas/60">
            <tr className="border-b border-black/5">
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold`}>
                Имя / Email
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[160px]`}>
                Роль
              </th>
              <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[150px]`}>
                Последний вход
              </th>
              {isAdmin && (
                <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[60px]`}>
                  {/* actions */}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr>
                <td colSpan={isAdmin ? 4 : 3} className="px-4 py-12 text-center">
                  <p className="text-sm text-muted-2">
                    Пользователей нет — это аномалия, как минимум вы
                    должны быть в списке.
                  </p>
                </td>
              </tr>
            )}
            {users.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                editableRole={isAdmin && u.id !== meQuery.data?.id}
                canDelete={isAdmin && u.id !== meQuery.data?.id}
                onRequestDelete={(target) => {
                  setDeleteError(null);
                  setDeleteTarget(target);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pending invites */}
      {pendingInvites.length > 0 && (
        <div>
          <h3 className={`${T.mono} uppercase text-muted-3 mb-2`}>
            Ожидают принятия приглашения
          </h3>
          <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-canvas/60">
                <tr className="border-b border-black/5">
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold`}>
                    Email
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[180px]`}>
                    Предложенная роль
                  </th>
                  <th className={`px-4 py-2.5 ${T.mono} uppercase text-muted-3 font-semibold w-[150px]`}>
                    Приглашён
                  </th>
                </tr>
              </thead>
              <tbody>
                {pendingInvites.map((i) => (
                  <tr
                    key={i.id}
                    className="border-b border-black/5 last:border-0"
                  >
                    <td className="px-4 py-3 align-middle">
                      <div className="flex items-center gap-2">
                        <Mail size={13} className="text-muted-3 shrink-0" />
                        <span className="text-sm text-ink">{i.email}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <span className="text-xs text-muted-2">
                        {ROLE_LABEL[i.suggested_role] ?? i.suggested_role}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-middle">
                      <span className="text-xs text-muted-3">
                        {relativeTime(i.created_at)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)} />
      {deleteTarget && (
        <DeleteUserModal
          name={deleteTarget.name || deleteTarget.email}
          busy={del.isPending}
          error={deleteError}
          onCancel={() => {
            setDeleteTarget(null);
            setDeleteError(null);
          }}
          onConfirm={performDelete}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// User row — name + role dropdown + last login
// ---------------------------------------------------------------------------

function UserRow({
  user,
  editableRole,
  canDelete,
  onRequestDelete,
}: {
  user: UserListItemOut;
  editableRole: boolean;
  canDelete: boolean;
  onRequestDelete: (u: UserListItemOut) => void;
}) {
  const change = useChangeUserRole();
  const [error, setError] = useState<string | null>(null);

  function onRoleChange(newRole: string) {
    if (newRole === user.role) return;
    setError(null);
    change.mutate(
      { id: user.id, body: { role: newRole as "admin" | "head" | "manager" } },
      {
        onError: (err: ApiError) => {
          const detail =
            err.body && typeof err.body === "object"
              ? (err.body as { detail?: unknown }).detail
              : null;
          if (
            detail &&
            typeof detail === "object" &&
            "code" in (detail as object) &&
            (detail as { code: string }).code === "last_admin"
          ) {
            setError(
              (detail as { message: string }).message ??
                "Это последний админ — повысьте кого-то ещё.",
            );
          } else {
            setError(
              typeof detail === "string"
                ? detail
                : "Не удалось сменить роль",
            );
          }
        },
      },
    );
  }

  const initial = (user.name || user.email).slice(0, 1).toUpperCase();

  return (
    <tr className="border-b border-black/5 last:border-0 hover:bg-canvas/40 transition-colors">
      <td className="px-4 py-3 align-middle">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
            <span className="text-xs font-bold text-brand-accent">{initial}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink truncate">
              {user.name || "—"}
            </p>
            <p className={`${T.mono} text-muted-3 truncate`}>
              {user.email}
            </p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3 align-middle">
        {editableRole ? (
          <div className="flex items-center gap-2">
            <select
              value={user.role}
              onChange={(e) => onRoleChange(e.target.value)}
              disabled={change.isPending}
              className="px-2 py-1 text-xs bg-white border border-black/10 rounded-lg outline-none focus:border-brand-accent/40 transition-colors disabled:opacity-40"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
            {change.isPending && (
              <Loader2 size={12} className="animate-spin text-muted-2" />
            )}
          </div>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-muted">
            {user.role === "admin" ? (
              <Shield size={11} className="text-brand-accent" />
            ) : (
              <UserCircle2 size={11} className="text-muted-3" />
            )}
            {ROLE_LABEL[user.role] ?? user.role}
          </span>
        )}
        {error && (
          <p className="text-xs text-rose mt-1 leading-tight">
            {error}
          </p>
        )}
      </td>
      <td className="px-4 py-3 align-middle">
        <span className="text-xs text-muted-3 font-mono">
          {relativeTime(user.last_login_at)}
        </span>
      </td>
      {canDelete && (
        <td className="px-4 py-3 align-middle text-right">
          <button
            type="button"
            onClick={() => onRequestDelete(user)}
            className="p-1.5 text-muted-3 hover:text-rose hover:bg-rose/5 rounded-lg transition-colors"
            aria-label="Удалить пользователя"
            title="Удалить"
          >
            <Trash2 size={14} />
          </button>
        </td>
      )}
    </tr>
  );
}

function DeleteUserModal({
  name,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  name: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl shadow-soft max-w-md w-full p-6">
        <h3 className="type-card-title text-ink mb-2">
          Удалить {name}?
        </h3>
        <p className="text-sm text-muted-2 mb-5">
          Все его активные лиды вернутся в пул. История активности и
          аудит-лог сохранятся.
        </p>
        {error && (
          <p className="text-xs text-rose mb-3 bg-rose/5 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-2 text-sm text-muted hover:bg-canvas/80 rounded-pill transition-colors disabled:opacity-40"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="px-4 py-2 text-sm font-semibold text-white bg-rose hover:bg-rose/90 rounded-pill transition-colors disabled:opacity-40 inline-flex items-center gap-1.5"
          >
            {busy && <Loader2 size={13} className="animate-spin" />}
            Удалить
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Invite modal
// ---------------------------------------------------------------------------

function InviteModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] =
    useState<"admin" | "head" | "manager">("manager");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const invite = useInviteUser();
  const busy = invite.isPending;

  if (!open) return null;

  function handleSend() {
    setError(null);
    const trimmed = email.trim();
    if (!trimmed) {
      setError("Почта обязательна");
      return;
    }
    const body: UserInviteIn = { email: trimmed, role };
    invite.mutate(body, {
      onSuccess: () => {
        setSent(true);
        setEmail("");
      },
      onError: (err: ApiError) => {
        const detail =
          err.body && typeof err.body === "object"
            ? (err.body as { detail?: unknown }).detail
            : null;
        if (
          detail &&
          typeof detail === "object" &&
          "code" in (detail as object) &&
          (detail as { code: string }).code === "invite_send_failed"
        ) {
          setError(
            (detail as { message: string }).message ??
              "Не удалось отправить приглашение. Попробуйте позже.",
          );
        } else {
          setError(
            typeof detail === "string"
              ? detail
              : "Не удалось отправить приглашение",
          );
        }
      },
    });
  }

  function handleClose() {
    if (busy) return;
    setEmail("");
    setRole("manager");
    setError(null);
    setSent(false);
    onClose();
  }

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50 backdrop-blur-[2px]"
        onClick={handleClose}
        aria-hidden
      />
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Пригласить пользователя"
          className="bg-white rounded-2xl border border-black/5 shadow-soft w-full max-w-md overflow-hidden"
        >
          <div className="px-6 py-4 border-b border-black/5 flex items-start justify-between gap-4">
            <div>
              <div className={`${T.mono} uppercase text-muted-3`}>
                Команда
              </div>
              <h2 className="type-card-title text-ink mt-0.5">
                Пригласить пользователя
              </h2>
            </div>
            <button
              onClick={handleClose}
              disabled={busy}
              className="shrink-0 p-1.5 -mr-1.5 rounded-lg text-muted-2 hover:bg-canvas hover:text-ink transition-colors disabled:opacity-40"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          </div>

          <div className="px-6 py-5 space-y-4">
            {sent ? (
              <div className="text-center py-4">
                <Mail size={28} className="mx-auto text-brand-accent mb-2" />
                <p className="text-sm font-semibold text-ink">
                  Приглашение отправлено
                </p>
                <p className="text-xs text-muted-2 mt-1">
                  Пользователь получит письмо со ссылкой для входа. После
                  первого входа он появится в списке команды как
                  «Менеджер» — измените роль здесь.
                </p>
              </div>
            ) : (
              <>
                <div>
                  <label className={`block ${T.mono} uppercase text-muted-3 mb-1.5`}>
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="manager@drinkx.tech"
                    className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-colors"
                  />
                </div>
                <div>
                  <label className={`block ${T.mono} uppercase text-muted-3 mb-1.5`}>
                    Предложенная роль
                  </label>
                  <select
                    value={role}
                    onChange={(e) =>
                      setRole(e.target.value as "admin" | "head" | "manager")
                    }
                    className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-brand-accent/40 transition-colors"
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-3 mt-1 leading-tight">
                    После принятия приглашения пользователь получит роль
                    «Менеджер». Эта подсказка для вас — в админке справа
                    можно изменить роль.
                  </p>
                </div>
              </>
            )}
            {error && (
              <p className="text-sm text-rose">{error}</p>
            )}
          </div>

          <div className="px-6 py-4 border-t border-black/5 flex items-center justify-end gap-2">
            {sent ? (
              <button
                onClick={handleClose}
                className="px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 transition-all duration-300"
              >
                Готово
              </button>
            ) : (
              <>
                <button
                  onClick={handleClose}
                  disabled={busy}
                  className="text-sm font-semibold text-muted hover:text-ink disabled:opacity-40 transition-colors"
                >
                  Отмена
                </button>
                <button
                  onClick={handleSend}
                  disabled={busy || !email.trim()}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-pill bg-ink text-white text-sm font-semibold hover:bg-ink/90 disabled:opacity-40 transition-all duration-300"
                >
                  {busy && <Loader2 size={14} className="animate-spin" />}
                  {busy ? "Отправляем…" : "Отправить приглашение"}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
