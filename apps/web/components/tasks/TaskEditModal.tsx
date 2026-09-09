"use client";

import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { useUpdateTask } from "@/lib/hooks/use-tasks";
import { useMe } from "@/lib/hooks/use-me";
import { useUsers } from "@/lib/hooks/use-users";
import { UserSelect } from "@/components/ui/UserSelect";
import { apiErrorDetail } from "@/lib/api-error";
import { C } from "@/lib/design-system";
import type { TaskPatchIn } from "@/lib/types";

interface Props {
  /** Пусто у задач без лида. */
  leadId: string | null;
  taskId: string;
  initialTitle: string;
  initialDueIso: string | null;
  /** Текущий исполнитель — селект показываем только head/admin. */
  initialAssigneeId?: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

/** datetime-local string (yyyy-mm-ddTHH:mm) in the browser's local TZ. */
function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function TaskEditModal({
  leadId,
  taskId,
  initialTitle,
  initialDueIso,
  initialAssigneeId = null,
  onClose,
  onSaved,
}: Props) {
  const update = useUpdateTask();
  const { data: me } = useMe();
  const { data: usersData } = useUsers();
  const canReassign = me?.role === "admin" || me?.role === "head";

  const [title, setTitle] = useState(initialTitle);
  const [due, setDue] = useState(() => isoToLocalInput(initialDueIso));
  const [assigneeId, setAssigneeId] = useState<string | null>(initialAssigneeId);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = title.trim();
    if (!trimmed) return;
    setError(null);

    // Шлём только реально изменившиеся поля — бэкенд отвечает 400
    // «нечего менять» на пустой PATCH.
    const body: TaskPatchIn = {};
    if (trimmed !== initialTitle) body.text = trimmed;

    const initialDueLocal = isoToLocalInput(initialDueIso);
    if (due !== initialDueLocal) {
      let iso: string | null = null;
      if (due) {
        const d = new Date(due); // datetime-local parsed in local time
        if (!Number.isNaN(d.getTime())) iso = d.toISOString();
      }
      body.task_due_at = iso;
    }

    if (canReassign && assigneeId !== initialAssigneeId) {
      body.assignee_user_id = assigneeId;
    }

    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }

    try {
      await update.mutateAsync({ taskId, leadId, body });
      onSaved?.();
      onClose();
    } catch (err) {
      setError(apiErrorDetail(err, "Не удалось сохранить задачу"));
    }
  }

  return (
    <Modal open onClose={onClose} title="Редактирование задачи" dismissOnBackdrop={false}>
      <div className="-m-6">
        <div className="flex items-center justify-between px-5 py-4 border-b border-brand-border">
          <h3 className="text-base font-bold">Редактирование задачи</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-brand-muted hover:text-brand-primary p-1"
            aria-label="Закрыть"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Название
            </label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && title.trim()) void handleSave();
              }}
              placeholder="Название задачи"
              className={`mt-1 ${C.form.field}`}
            />
          </div>

          <div>
            <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
              Срок и время
            </label>
            <input
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              aria-label="Срок и время"
              className={`mt-1 ${C.form.field}`}
            />
            {due && (
              <button
                type="button"
                onClick={() => setDue("")}
                className="mt-1 text-xs text-brand-muted hover:text-brand-primary"
              >
                Очистить срок
              </button>
            )}
          </div>

          {canReassign && (
            <div>
              <label className="text-xs font-mono uppercase tracking-wide text-brand-muted">
                Исполнитель
              </label>
              <UserSelect
                value={assigneeId}
                onChange={setAssigneeId}
                users={usersData?.items ?? []}
                meId={me?.id}
                aria-label="Исполнитель"
                className="mt-1"
              />
            </div>
          )}

          {error && <p className="text-xs text-rose">{error}</p>}

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={!title.trim() || update.isPending}
              className={`${C.button.primary} type-body px-4 py-2 disabled:opacity-40`}
            >
              {update.isPending && (
                <Loader2 size={13} className="animate-spin inline-block mr-1.5" />
              )}
              Сохранить
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={update.isPending}
              className="text-sm text-brand-muted hover:text-brand-primary disabled:opacity-40"
            >
              Отмена
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
