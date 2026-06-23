"use client";
import { useState } from "react";
import { Loader2, CalendarClock } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { useCreateLeadTask } from "@/lib/hooks/use-lead-tasks";
import { C } from "@/lib/design-system";

// Bitrix-style «plan the next step» prompt. Shown when the manager leaves a
// lead card that has no open task. «Поставить задачу» creates a task and
// proceeds; «Пропустить» just proceeds. Both call back into LeadCard, which
// completes the original navigation.

function defaultDue(): string {
  // Tomorrow 18:00 local, as a datetime-local string (yyyy-mm-ddTHH:mm).
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(18, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function NextStepPrompt({
  leadId,
  company,
  onSaved,
  onSkip,
}: {
  leadId: string;
  company: string;
  onSaved: () => void;
  onSkip: () => void;
}) {
  const create = useCreateLeadTask(leadId);
  const [text, setText] = useState("");
  const [due, setDue] = useState(defaultDue);

  async function handleSave() {
    const title = text.trim();
    if (!title || create.isPending) return;
    try {
      await create.mutateAsync({
        text: title,
        task_due_at: due ? new Date(due).toISOString() : null,
      });
      onSaved();
    } catch {
      /* keep the modal open; error surfaced via mutation state */
    }
  }

  return (
    <Modal
      open
      onClose={onSkip}
      title="Запланируйте следующий шаг"
      size="max-w-md"
      dismissOnBackdrop={false}
    >
      <div className="space-y-4">
        <div>
          <h2 className={`type-card-title ${C.color.text}`}>Запланируйте следующий шаг</h2>
          <p className={`type-caption ${C.color.muted} mt-1`}>
            По клиенту «{company}» нет запланированной задачи. Поставьте следующий
            шаг, чтобы не потерять сделку.
          </p>
        </div>

        <div className="space-y-2">
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleSave();
            }}
            placeholder="Например: позвонить, отправить КП…"
            className={C.form.field}
          />
          <label className="flex items-center gap-2 type-caption text-brand-muted px-1">
            <CalendarClock size={14} />
            <input
              type="datetime-local"
              value={due}
              onChange={(e) => setDue(e.target.value)}
              aria-label="Срок задачи"
              className="bg-white border border-brand-border rounded-lg px-2 py-1.5 type-caption text-brand-primary outline-none focus:border-brand-accent"
            />
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onSkip}
            className={`px-4 py-2 type-caption font-semibold ${C.button.ghost}`}
          >
            Пропустить
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!text.trim() || create.isPending}
            className={`inline-flex items-center gap-1.5 px-4 py-2 type-caption font-semibold text-white ${C.button.primary} disabled:opacity-50`}
          >
            {create.isPending && <Loader2 size={14} className="animate-spin" />}
            Поставить задачу
          </button>
        </div>
      </div>
    </Modal>
  );
}
