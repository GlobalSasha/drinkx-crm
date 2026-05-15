"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useDeleteLead } from "@/lib/hooks/use-lead";
import { ApiError } from "@/lib/api-client";
import { C } from "@/lib/design-system";
import { Modal } from "@/components/ui/Modal";

interface Props {
  leadId: string;
  companyName: string;
  onClose: () => void;
}

/**
 * Two-step confirm: manager must type the company name to enable Delete.
 * On success, navigates back to /pipeline — the lead row is gone.
 */
export function DeleteConfirmModal({ leadId, companyName, onClose }: Props) {
  const del = useDeleteLead(leadId);
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ok = typed.trim().toLowerCase() === companyName.trim().toLowerCase();

  function handleDelete() {
    setError(null);
    del.mutate(undefined, {
      onSuccess: () => router.push("/pipeline"),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError("Лид уже удалён");
        } else {
          setError("Не удалось удалить лид");
        }
      },
    });
  }

  return (
    <Modal open onClose={onClose} title="Удалить лид?" dismissOnBackdrop={false}>
      <>
        <div className="flex items-start gap-3 mb-4">
          <div className="p-2 rounded-full bg-rose/10 shrink-0">
            <AlertTriangle size={20} className="text-rose" />
          </div>
          <div>
            <h2 className={`type-card-title ${C.color.text}`}>
              Удалить лид?
            </h2>
            <p className={`type-caption ${C.color.muted} mt-1`}>
              Действие нельзя отменить. Все связанные контакты, активности
              и follow-up&apos;ы будут удалены вместе с лидом.
            </p>
          </div>
        </div>

        <div className="mb-4">
          <label
            htmlFor="confirm-delete-name"
            className="type-caption text-brand-muted block mb-1.5"
          >
            Введите название компании для подтверждения
          </label>
          <input
            id="confirm-delete-name"
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={companyName}
            className="w-full px-3 py-2 type-caption text-brand-muted bg-white border border-brand-border rounded-xl outline-none focus:border-rose transition-colors"
            autoFocus
          />
        </div>

        {error && (
          <p className="type-caption text-rose mb-3">{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={del.isPending}
            className={`px-4 py-1.5 type-body font-semibold ${C.button.ghost} transition-opacity`}
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={!ok || del.isPending}
            className="px-4 py-1.5 type-body font-semibold bg-rose text-white rounded-full disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {del.isPending ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </>
    </Modal>
  );
}
