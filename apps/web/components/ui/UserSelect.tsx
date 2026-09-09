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
      {users.map((user) => (
        <option key={user.id} value={user.id}>
          {(user.name || user.email) + " · " + (ROLE_LABEL[user.role] ?? user.role)}
          {user.id === meId ? " (вы)" : ""}
        </option>
      ))}
    </select>
  );
}
