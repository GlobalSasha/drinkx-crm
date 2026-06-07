"use client";

import { useState } from "react";
import { Loader2, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { useUpdateLeadTask } from "@/lib/hooks/use-lead-tasks";
import { C } from "@/lib/design-system";

interface Props {
  leadId: string;
  taskId: string;
  initialTitle: string;
  initialDueIso: string | null;
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
  onClose,
  onSaved,
}: Props) {
  const update = useUpdateLeadTask(leadId);
  const [title, setTitle] = useState(initialTitle);
  const [due, setDue] = useState(() => isoToLocalInput(initialDueIso));
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = title.trim();
    if (!trimmed) return;
    setError(null);
    let iso: string | null = null;
    if (due) {
      const d = new Date(due); // datetime-local parsed in local time
      if (!Number.isNaN(d.getTime())) iso = d.toISOString();
    }
    try {
      await update.mutateAsync({ activityId: taskId, body: trimmed, task_due_at: iso });
      onSaved?.();
      onClose();
    } catch {
      setError("Не удалось сохранить задачу.");
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
