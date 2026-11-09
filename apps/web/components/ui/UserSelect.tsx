"use client";

import { C } from "@/lib/design-system";
import type { UserListItemOut } from "@/lib/types";

const ROLE_LABEL: Record<string, string> = {
  admin: "Админ",
  head: "Руководитель",
  manager: "Менеджер",
};

export interface UserSelectProps {
  value: string | null;
  onChange: (id: string | null) => void;
  users: UserListItemOut[];
  /** id текущего пользователя — подпись «(вы)». */
  meId?: string;
  /** Владелец лида, к которому относится выбор. Если передан, менеджер,
   *  которому лид не принадлежит, получает пометку: карточку он не откроет. */
  leadOwnerId?: string | null;
  /** Пункт «— не выбран —» / своя подпись пустого значения. */
  allowEmpty?: boolean;
  emptyLabel?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  className?: string;
}

export function UserSelect({
  value,
  onChange,
  users,
  meId,
  leadOwnerId,
  allowEmpty,
  emptyLabel = "— не выбран —",
  disabled,
  id,
  "aria-label": ariaLabel,
  className,
}: UserSelectProps) {
  return (
    <select
      id={id}
      aria-label={ariaLabel}
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value || null)}
      className={`${C.form.field}${className ? ` ${className}` : ""}`}
    >
      {allowEmpty && <option value="">{emptyLabel}</option>}
      {!allowEmpty && value == null && (
        <option value="" disabled hidden>
          — выберите —
        </option>
      )}
      {users.map((user) => (
        <option key={user.id} value={user.id}>
          {(user.name || user.email) + " · " + (ROLE_LABEL[user.role] ?? user.role)}
          {user.id === meId ? " (вы)" : ""}
          {leadOwnerId !== undefined && user.role === "manager" && user.id !== leadOwnerId
            ? " · не видит карточку"
            : ""}
        </option>
      ))}
    </select>
  );
}
