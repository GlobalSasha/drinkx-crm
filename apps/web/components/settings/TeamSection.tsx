"use client";
// TeamSection — Sprint 2.4 G1.
//
// Renders the workspace's users + pending invites as a single table.
// All roles can read; admin-only sees the «+ Пригласить» CTA, the
// inline role dropdown, and (eventually) the «Удалить» action. Friendly
// modals consume the backend's structured errors:
//   - 502 {code: invite_send_failed}  → «retry later»
//   - 409 {code: last_admin}         → «promote someone else first»
import { useState } from "react";
import { Loader2, Mail, Plus, Shield, UserCircle2, X } from "lucide-react";

import { ApiError } from "@/lib/api-client";
import { useMe } from "@/lib/hooks/use-me";
import {
  useChangeUserRole,
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
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.max(0, Math.round((now - then) / 1000));
  if (sec < 60) return "сейчас";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} мин назад`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} ч назад`;
  const day = Math.round(hr / 24);
  return `${day} дн назад`;
}

export function TeamSection() {
  const meQuery = useMe();
  const usersQuery = useUsers();
  const invitesQuery = useUserInvites();

  const isAdmin = meQuery.data?.role === "admin";
  const users = usersQuery.data?.items ?? [];
  const invites = invitesQuery.data ?? [];
  // Show pending invites only — accepted ones already have a User row.
  const pendingInvites = invites.filter((i) => !i.accepted_at);

  const [inviteOpen, setInviteOpen] = useState(false);

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
          <h2 className="text-lg font-extrabold tracking-tight">Команда</h2>
          <p className="text-xs text-muted-2 mt-0.5">
            Все пользователи общего workspace. Админ может приглашать
            новых членов и менять роли.
          </p>
        </div>
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

      {/* Users table */}
      <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-canvas/60">
            <tr className="border-b border-black/5">
              <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold">
                Имя / Email
              </th>
              <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold w-[160px]">
                Роль
              </th>
              <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold w-[150px]">
                Последний вход
              </th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-12 text-center">
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
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pending invites */}
      {pendingInvites.length > 0 && (
        <div>
          <h3 className="text-xs font-mono uppercase tracking-[0.15em] text-muted-3 mb-2">
            Ожидают принятия приглашения
          </h3>
          <div className="bg-white border border-black/5 rounded-2xl shadow-soft overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-canvas/60">
                <tr className="border-b border-black/5">
                  <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold">
                    Email
                  </th>
                  <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold w-[180px]">
                    Предложенная роль
                  </th>
                  <th className="px-4 py-2.5 font-mono uppercase tracking-[0.2em] text-[10px] text-muted-3 font-semibold w-[150px]">
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// User row — name + role dropdown + last login
// ---------------------------------------------------------------------------

function UserRow({
  user,
  editableRole,
}: {
  user: UserListItemOut;
  editableRole: boolean;
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
          <div className="w-7 h-7 rounded-full bg-accent/15 flex items-center justify-center shrink-0">
            <span className="text-[11px] font-bold text-accent">{initial}</span>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink truncate">
              {user.name || "—"}
            </p>
            <p className="text-[11px] font-mono text-muted-3 truncate">
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
              className="px-2 py-1 text-xs bg-white border border-black/10 rounded-lg outline-none focus:border-accent/40 transition-colors disabled:opacity-40"
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
              <Shield size={11} className="text-accent" />
            ) : (
              <UserCircle2 size={11} className="text-muted-3" />
            )}
            {ROLE_LABEL[user.role] ?? user.role}
          </span>
        )}
        {error && (
          <p className="text-[11px] text-red-700 mt-1 leading-tight">
            {error}
          </p>
        )}
      </td>
      <td className="px-4 py-3 align-middle">
        <span className="text-xs text-muted-3 font-mono">
          {relativeTime(user.last_login_at)}
        </span>
      </td>
    </tr>
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
              <div className="text-[10px] font-mono uppercase tracking-wider text-muted-3">
                Команда
              </div>
              <h2 className="text-lg font-extrabold tracking-tight text-ink mt-0.5">
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
                <Mail size={28} className="mx-auto text-accent mb-2" />
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
                  <label className="block text-[11px] font-mono uppercase tracking-wide text-muted-3 mb-1.5">
                    Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="manager@drinkx.tech"
                    className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-colors"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-mono uppercase tracking-wide text-muted-3 mb-1.5">
                    Предложенная роль
                  </label>
                  <select
                    value={role}
                    onChange={(e) =>
                      setRole(e.target.value as "admin" | "head" | "manager")
                    }
                    className="w-full px-3 py-2 text-sm bg-white border border-black/10 rounded-xl outline-none focus:border-accent/40 transition-colors"
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                  <p className="text-[11px] text-muted-3 mt-1 leading-tight">
                    После принятия приглашения пользователь получит роль
                    «Менеджер». Эта подсказка для вас — в админке справа
                    можно изменить роль.
                  </p>
                </div>
              </>
            )}
            {error && (
              <p className="text-[12px] text-red-700">{error}</p>
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
